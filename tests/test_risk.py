"""Stage 5 risk manager tests: sizers, daily loss guard, manager wiring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from money_maker.live.orders import Order, OrderStatus
from money_maker.live.paper_executor import PaperExecutor
from money_maker.live.risk import (
    AtrSizer,
    DailyLossGuard,
    FixedFractionSizer,
    RiskManager,
)
from money_maker.live.router import SimulatedRouter
from money_maker.live.signal_engine import SignalEvent


class _SlipRouter:
    """Fills at ref_price * (1 + slip), so we can assert slippage bps.

    Also records the quote_qty each buy received, for sizing assertions.
    """

    def __init__(self, slip: float = 0.0):
        self.slip = slip
        self.buy_quotes: list[float] = []

    async def buy(self, symbol: str, quote_qty: float, ref_price: float) -> Order:
        self.buy_quotes.append(quote_qty)
        fill = ref_price * (1 + self.slip)
        qty = quote_qty / fill
        return Order(client_id="b", symbol=symbol, side="BUY", qty=qty,
                     filled_qty=qty, avg_price=fill, status=OrderStatus.FILLED)

    async def sell(self, symbol: str, base_qty: float, ref_price: float) -> Order:
        fill = ref_price * (1 + self.slip)
        return Order(client_id="s", symbol=symbol, side="SELL", qty=base_qty,
                     filled_qty=base_qty, avg_price=fill, status=OrderStatus.FILLED)

    async def get_free_balance(self, asset: str) -> float:
        return 0.0


def _sig(desired: int, t_off: int, close: float, atr: float | None = None) -> SignalEvent:
    return SignalEvent(
        timestamp=datetime(2026, 1, 1, 0, t_off, tzinfo=UTC),
        symbol="BTCUSDT",
        desired_position=desired,
        last_close=close,
        atr=atr,
    )


# --------------------------------------------------------------------------- #
# FixedFractionSizer
# --------------------------------------------------------------------------- #
def test_fixed_sizer_always_returns_full_budget():
    s = FixedFractionSizer(max_position_usdt=100.0)
    assert s.size(price=100.0, atr=1.0) == 100.0
    assert s.size(price=50000.0, atr=None) == 100.0


# --------------------------------------------------------------------------- #
# AtrSizer
# --------------------------------------------------------------------------- #
def test_atr_sizer_shrinks_when_volatility_high():
    s = AtrSizer(max_position_usdt=100.0, target_vol_pct=0.005)
    # vol = atr/price = 1/100 = 0.01 = 2x target -> half size
    assert s.size(price=100.0, atr=1.0) == pytest.approx(50.0)


def test_atr_sizer_caps_at_max_when_volatility_low():
    s = AtrSizer(max_position_usdt=100.0, target_vol_pct=0.005)
    # vol = 0.25/100 = 0.0025 = half target -> would be 2x, capped at max
    assert s.size(price=100.0, atr=0.25) == pytest.approx(100.0)


def test_atr_sizer_falls_back_to_full_when_atr_missing():
    s = AtrSizer(max_position_usdt=100.0, target_vol_pct=0.005)
    assert s.size(price=100.0, atr=None) == 100.0
    assert s.size(price=100.0, atr=0.0) == 100.0


# --------------------------------------------------------------------------- #
# DailyLossGuard
# --------------------------------------------------------------------------- #
def test_daily_guard_allows_until_limit_hit():
    g = DailyLossGuard(max_daily_loss_usdt=20.0)
    t0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    assert g.can_trade(t0) is True
    g.record(-10.0, t0)
    assert g.can_trade(t0) is True
    g.record(-15.0, t0)  # cum -25 < -20
    assert g.can_trade(t0) is False


def test_daily_guard_resets_next_utc_day():
    g = DailyLossGuard(max_daily_loss_usdt=20.0)
    t0 = datetime(2026, 1, 1, 23, 0, tzinfo=UTC)
    g.record(-25.0, t0)
    assert g.can_trade(t0) is False
    t1 = t0 + timedelta(hours=2)  # next day
    assert g.can_trade(t1) is True


def test_daily_guard_zero_limit_means_unlimited():
    g = DailyLossGuard(max_daily_loss_usdt=0.0)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    g.record(-1000.0, t0)
    assert g.can_trade(t0) is True


def test_daily_guard_profit_does_not_trip():
    g = DailyLossGuard(max_daily_loss_usdt=20.0)
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    g.record(+50.0, t0)
    g.record(-30.0, t0)  # cum +20, still positive
    assert g.can_trade(t0) is True


# --------------------------------------------------------------------------- #
# RiskManager
# --------------------------------------------------------------------------- #
def test_risk_manager_blocks_entry_after_loss_limit():
    rm = RiskManager(
        sizer=FixedFractionSizer(100.0),
        daily_guard=DailyLossGuard(20.0),
    )
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    assert rm.allow_entry(t0) is True
    assert rm.size_for(price=100.0, atr=1.0) == 100.0

    class _T:
        pnl_quote = -25.0

    rm.on_trade_closed(_T(), t0)
    assert rm.allow_entry(t0) is False


# --------------------------------------------------------------------------- #
# Slippage measurement (PaperExecutor)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_slippage_zero_on_simulated_router():
    exe = PaperExecutor(router=SimulatedRouter(), max_position_usdt=100.0)
    await exe.on_signal(_sig(1, 0, 100.0))
    await exe.on_signal(_sig(0, 5, 110.0))
    tr = exe.trades[0]
    assert tr.entry_slip_bps == pytest.approx(0.0)
    assert tr.exit_slip_bps == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_slippage_recorded_from_fill_vs_signal_price():
    router = _SlipRouter(slip=0.001)  # fills 10 bps above signal price
    exe = PaperExecutor(router=router, max_position_usdt=100.0)
    await exe.on_signal(_sig(1, 0, 100.0))
    await exe.on_signal(_sig(0, 5, 110.0))
    tr = exe.trades[0]
    assert tr.entry_slip_bps == pytest.approx(10.0)
    assert tr.exit_slip_bps == pytest.approx(10.0)


# --------------------------------------------------------------------------- #
# RiskManager wired into PaperExecutor
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_executor_uses_atr_sizer_for_order_quote():
    router = _SlipRouter(slip=0.0)
    rm = RiskManager(
        sizer=AtrSizer(max_position_usdt=100.0, target_vol_pct=0.005),
        daily_guard=DailyLossGuard(0.0),
    )
    exe = PaperExecutor(router=router, max_position_usdt=100.0, risk=rm)
    # vol = atr/price = 1/100 = 0.01 = 2x target → half size = 50
    await exe.on_signal(_sig(1, 0, 100.0, atr=1.0))
    assert router.buy_quotes[0] == pytest.approx(50.0)


@pytest.mark.asyncio
async def test_executor_blocks_entry_after_daily_loss_but_allows_exit():
    router = SimulatedRouter()
    rm = RiskManager(
        sizer=FixedFractionSizer(100.0),
        daily_guard=DailyLossGuard(20.0),
    )
    exe = PaperExecutor(router=router, max_position_usdt=100.0, risk=rm)

    # Trade 1: lose 25 USDT → trips the daily guard.
    await exe.on_signal(_sig(1, 0, 100.0))
    await exe.on_signal(_sig(0, 5, 75.0))  # -25 USDT
    assert exe.trades[0].pnl_quote == pytest.approx(-25.0)
    assert rm.allow_entry(datetime(2026, 1, 1, 0, 6, tzinfo=UTC)) is False

    # New entry now blocked.
    blocked = await exe.on_signal(_sig(1, 10, 100.0))
    assert blocked is None
    assert exe.position == 0


@pytest.mark.asyncio
async def test_executor_allows_exit_even_when_guard_tripped():
    rm = RiskManager(
        sizer=FixedFractionSizer(100.0),
        daily_guard=DailyLossGuard(20.0),
    )
    exe = PaperExecutor(router=SimulatedRouter(), max_position_usdt=100.0, risk=rm)
    # Open while still allowed.
    opened = await exe.on_signal(_sig(1, 0, 100.0))
    assert opened is not None and exe.position == 1

    # Now trip the guard from prior (external) losses.
    rm.daily_guard.record(-100.0, datetime(2026, 1, 1, 0, 1, tzinfo=UTC))
    assert rm.allow_entry(datetime(2026, 1, 1, 0, 2, tzinfo=UTC)) is False

    # The exit must still go through — never trap a held position.
    sell = await exe.on_signal(_sig(0, 3, 90.0))
    assert sell is not None and sell.side == "SELL"
    assert exe.position == 0


# --------------------------------------------------------------------------- #
# Kill switch — liquidate base balance
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_simulated_router_tracks_holdings():
    r = SimulatedRouter()
    await r.buy("BTCUSDT", quote_qty=100.0, ref_price=50.0)  # +2 BTC
    assert await r.get_free_balance("BTC") == pytest.approx(2.0)
    await r.sell("BTCUSDT", base_qty=2.0, ref_price=50.0)
    assert await r.get_free_balance("BTC") == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_liquidate_sells_entire_base_balance():
    from money_maker.live.kill import liquidate

    r = SimulatedRouter()
    await r.buy("BTCUSDT", quote_qty=100.0, ref_price=50.0)  # +2 BTC
    order = await liquidate(r, "BTCUSDT", quote_asset="USDT", ref_price=50.0)
    assert order is not None and order.side == "SELL"
    assert order.filled_qty == pytest.approx(2.0)
    assert await r.get_free_balance("BTC") == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_liquidate_noop_when_flat():
    from money_maker.live.kill import liquidate

    r = SimulatedRouter()
    order = await liquidate(r, "BTCUSDT", quote_asset="USDT", ref_price=50.0)
    assert order is None
