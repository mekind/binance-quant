"""Translate SignalEvents into actual orders via an OrderRouter.

Idempotency: we only act when the signal's `desired_position` differs from
our currently held one. The SignalEngine already deduplicates upstream, but
the executor enforces it again — defensive, since a future input source
(REST poll, replay) might not.

Trade ledger: every completed buy/sell pair is closed into a Trade record
with entry, exit, and net PnL (ignoring fees — those depend on the router).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger

from .orders import Order
from .risk import RiskManager
from .router import OrderRouter
from .signal_engine import SignalEvent


def _slip_bps(fill_price: float, signal_price: float) -> float:
    """Signed slippage in basis points: positive = filled worse-than-signal for a buy."""
    if signal_price <= 0:
        return 0.0
    return (fill_price / signal_price - 1.0) * 1e4


@dataclass(frozen=True, slots=True)
class Trade:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    qty: float
    pnl_quote: float           # in quote currency (USDT)
    pnl_pct: float
    entry_slip_bps: float = 0.0  # entry fill vs entry signal price
    exit_slip_bps: float = 0.0   # exit fill vs exit signal price


@dataclass
class PaperExecutor:
    router: OrderRouter
    max_position_usdt: float
    risk: RiskManager | None = None
    position: int = 0           # {0, 1}
    open_order: Order | None = None
    open_signal_time: datetime | None = None
    open_signal_price: float = 0.0
    trades: list[Trade] = field(default_factory=list)

    async def on_signal(self, ev: SignalEvent) -> Order | None:
        if ev.desired_position == self.position:
            return None

        if ev.desired_position == 1 and self.position == 0:
            if self.risk is not None and not self.risk.allow_entry(ev.timestamp):
                logger.warning(
                    f"entry blocked by risk manager (daily loss cut) @ {ev.timestamp}"
                )
                return None
            quote = (
                self.risk.size_for(ev.last_close, ev.atr)
                if self.risk is not None
                else self.max_position_usdt
            )
            order = await self.router.buy(ev.symbol, quote, ev.last_close)
            self.open_order = order
            self.open_signal_time = ev.timestamp
            self.open_signal_price = ev.last_close
            self.position = 1
            logger.info(
                f"BUY {order.symbol} qty={order.filled_qty:.6f} @ {order.avg_price:.2f} "
                f"(quote=${quote:.2f} slip={_slip_bps(order.avg_price, ev.last_close):+.1f}bps)"
            )
            return order

        if ev.desired_position == 0 and self.position == 1 and self.open_order is not None:
            entry = self.open_order
            order = await self.router.sell(ev.symbol, entry.filled_qty, ev.last_close)
            self.position = 0
            pnl_quote = (order.avg_price - entry.avg_price) * order.filled_qty
            pnl_pct = (order.avg_price / entry.avg_price - 1.0) if entry.avg_price > 0 else 0.0
            trade = Trade(
                symbol=ev.symbol,
                entry_time=self.open_signal_time or ev.timestamp,
                exit_time=ev.timestamp,
                entry_price=entry.avg_price,
                exit_price=order.avg_price,
                qty=order.filled_qty,
                pnl_quote=pnl_quote,
                pnl_pct=pnl_pct,
                entry_slip_bps=_slip_bps(entry.avg_price, self.open_signal_price),
                exit_slip_bps=_slip_bps(order.avg_price, ev.last_close),
            )
            self.trades.append(trade)
            if self.risk is not None:
                self.risk.on_trade_closed(trade, ev.timestamp)
            self.open_order = None
            self.open_signal_time = None
            self.open_signal_price = 0.0
            logger.info(
                f"SELL {order.symbol} qty={order.filled_qty:.6f} @ {order.avg_price:.2f} "
                f"pnl={pnl_quote:+.2f} ({pnl_pct:+.2%}) "
                f"slip={trade.exit_slip_bps:+.1f}bps"
            )
            return order

        # Defensive: state mismatch (e.g. desired=0 but position=0 already).
        return None

    def realized_pnl(self) -> float:
        return sum(t.pnl_quote for t in self.trades)

    def avg_slippage_bps(self) -> tuple[float, float]:
        """Mean (entry, exit) slippage in bps across closed trades; (0, 0) if none."""
        if not self.trades:
            return (0.0, 0.0)
        n = len(self.trades)
        entry = sum(t.entry_slip_bps for t in self.trades) / n
        exit_ = sum(t.exit_slip_bps for t in self.trades) / n
        return (entry, exit_)
