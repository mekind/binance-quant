"""Stage 5 risk management: position sizing, daily loss cut.

Three small, independently-testable units:

  - PositionSizer (Protocol): price + ATR -> quote (USDT) order size.
      FixedFractionSizer  — always the full budget (Stage 4 behaviour).
      AtrSizer            — volatility targeting: shrink size when the bar's
                            ATR-implied volatility exceeds a target.
  - DailyLossGuard        — trips when cumulative realized loss for the current
                            UTC day reaches the configured limit; auto-resets
                            at the UTC day boundary.
  - RiskManager           — composes a sizer + a loss guard for the executor to
                            consult: allow_entry / size_for / on_trade_closed.

Everything here is pure and synchronous so it can be unit-tested without a
network, an event loop, or a clock.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class PositionSizer(Protocol):
    def size(self, price: float, atr: float | None) -> float:
        """Return the order size in quote currency (USDT)."""
        ...


class FixedFractionSizer:
    """Always commit the full budget — preserves the Stage 4 behaviour."""

    def __init__(self, max_position_usdt: float):
        self.max_position_usdt = max_position_usdt

    def size(self, price: float, atr: float | None) -> float:
        del price, atr
        return self.max_position_usdt


class AtrSizer:
    """Volatility targeting. Scale the budget so realized per-bar volatility
    sits near `target_vol_pct`. When current volatility is higher, take a
    smaller position; never exceed the budget.

        vol  = atr / price
        size = max_position_usdt * min(1, target_vol_pct / vol)

    Falls back to the full budget when ATR is unknown or non-positive.
    """

    def __init__(self, max_position_usdt: float, target_vol_pct: float = 0.005):
        if target_vol_pct <= 0:
            raise ValueError("target_vol_pct must be > 0")
        self.max_position_usdt = max_position_usdt
        self.target_vol_pct = target_vol_pct

    def size(self, price: float, atr: float | None) -> float:
        if atr is None or atr <= 0 or price <= 0:
            return self.max_position_usdt
        vol = atr / price
        scale = min(1.0, self.target_vol_pct / vol)
        return self.max_position_usdt * scale


class DailyLossGuard:
    """Block new entries once the day's realized loss hits the limit.

    Tracks cumulative realized PnL for the current UTC date. A limit of 0
    disables the guard (unlimited). Exits are never blocked by this guard —
    the caller only consults it for entries.
    """

    def __init__(self, max_daily_loss_usdt: float):
        self.max_daily_loss_usdt = max_daily_loss_usdt
        self._day: date | None = None
        self._cum_pnl: float = 0.0

    def _roll(self, now: datetime) -> None:
        today = now.date()
        if self._day != today:
            self._day = today
            self._cum_pnl = 0.0

    def record(self, pnl: float, now: datetime) -> None:
        self._roll(now)
        self._cum_pnl += pnl

    def can_trade(self, now: datetime) -> bool:
        if self.max_daily_loss_usdt <= 0:
            return True
        self._roll(now)
        return self._cum_pnl > -self.max_daily_loss_usdt


class RiskManager:
    """Compose a sizer and a daily loss guard for the executor."""

    def __init__(self, sizer: PositionSizer, daily_guard: DailyLossGuard):
        self.sizer = sizer
        self.daily_guard = daily_guard

    def allow_entry(self, now: datetime) -> bool:
        return self.daily_guard.can_trade(now)

    def size_for(self, price: float, atr: float | None) -> float:
        return self.sizer.size(price, atr)

    def on_trade_closed(self, trade, now: datetime) -> None:
        self.daily_guard.record(trade.pnl_quote, now)
