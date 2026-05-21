"""Stage 4 part 3 tests — order state machine + PaperExecutor flow."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from money_maker.live.orders import (
    Order,
    OrderStatus,
    apply_fill,
    cancel,
    reject,
)
from money_maker.live.paper_executor import PaperExecutor
from money_maker.live.router import SimulatedRouter
from money_maker.live.signal_engine import SignalEvent


def _new_order(qty: float = 1.0, side: str = "BUY") -> Order:
    return Order(client_id="c1", symbol="BTCUSDT", side=side, qty=qty)


def test_partial_then_full_fill_transitions_correctly():
    o = _new_order(qty=1.0)
    o = apply_fill(o, 0.3, 30_000.0)
    assert o.status is OrderStatus.PARTIALLY_FILLED
    assert o.filled_qty == pytest.approx(0.3)
    assert o.avg_price == pytest.approx(30_000.0)

    o = apply_fill(o, 0.7, 31_000.0)
    assert o.status is OrderStatus.FILLED
    assert o.filled_qty == pytest.approx(1.0)
    # weighted avg of 0.3@30000 + 0.7@31000
    assert o.avg_price == pytest.approx(30_700.0)


def test_apply_fill_rejects_bad_inputs():
    o = _new_order()
    with pytest.raises(ValueError):
        apply_fill(o, 0.0, 100.0)
    with pytest.raises(ValueError):
        apply_fill(o, 1.0, 0.0)


def test_terminal_orders_ignore_further_mutations():
    o = apply_fill(_new_order(qty=1.0), 1.0, 30_000.0)
    assert o.status is OrderStatus.FILLED
    # apply_fill on a terminal order returns it unchanged
    assert apply_fill(o, 0.1, 50_000.0) is o
    assert cancel(o) is o
    assert reject(o) is o


def test_cancel_and_reject_only_from_open():
    o = _new_order()
    canc = cancel(o)
    assert canc.status is OrderStatus.CANCELED
    rej = reject(o)
    assert rej.status is OrderStatus.REJECTED
    # Idempotent on their own terminal state
    assert cancel(canc) is canc
    assert reject(rej) is rej


def test_simulated_router_fills_immediately():
    import asyncio
    r = SimulatedRouter()
    o = asyncio.run(r.buy("BTCUSDT", quote_qty=100.0, ref_price=50.0))
    assert o.status is OrderStatus.FILLED
    assert o.filled_qty == pytest.approx(2.0)
    assert o.avg_price == pytest.approx(50.0)
    assert r.filled == [o]


def test_simulated_router_validates_inputs():
    import asyncio
    r = SimulatedRouter()
    with pytest.raises(ValueError):
        asyncio.run(r.buy("X", 0.0, 100.0))
    with pytest.raises(ValueError):
        asyncio.run(r.sell("X", 1.0, 0.0))


def _signal(desired: int, t_offset: int = 0, close: float = 100.0) -> SignalEvent:
    return SignalEvent(
        timestamp=datetime(2025, 1, 1, 0, t_offset, tzinfo=UTC),
        symbol="BTCUSDT",
        desired_position=desired,
        last_close=close,
    )


@pytest.mark.asyncio
async def test_executor_open_then_close_records_trade_pnl():
    exe = PaperExecutor(router=SimulatedRouter(), max_position_usdt=100.0)

    # Open at $100 → qty = 1.0
    o1 = await exe.on_signal(_signal(1, t_offset=0, close=100.0))
    assert o1 is not None and o1.side == "BUY"
    assert exe.position == 1
    assert len(exe.trades) == 0

    # Close at $110 → +10% PnL, +10 USDT
    o2 = await exe.on_signal(_signal(0, t_offset=10, close=110.0))
    assert o2 is not None and o2.side == "SELL"
    assert exe.position == 0
    assert len(exe.trades) == 1

    trade = exe.trades[0]
    assert trade.entry_price == pytest.approx(100.0)
    assert trade.exit_price == pytest.approx(110.0)
    assert trade.pnl_quote == pytest.approx(10.0)
    assert trade.pnl_pct == pytest.approx(0.10)
    assert exe.realized_pnl() == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_executor_ignores_redundant_signals():
    exe = PaperExecutor(router=SimulatedRouter(), max_position_usdt=100.0)
    # Two "stay flat" signals in a row → no orders
    assert await exe.on_signal(_signal(0, 0, 100.0)) is None
    assert await exe.on_signal(_signal(0, 1, 105.0)) is None
    assert exe.position == 0
    assert exe.trades == []

    # Open long, then a repeated "stay long" → ignored
    await exe.on_signal(_signal(1, 2, 100.0))
    assert await exe.on_signal(_signal(1, 3, 101.0)) is None
    assert exe.position == 1
    assert exe.open_order is not None


@pytest.mark.asyncio
async def test_executor_records_loss_correctly():
    exe = PaperExecutor(router=SimulatedRouter(), max_position_usdt=100.0)
    await exe.on_signal(_signal(1, 0, close=100.0))
    await exe.on_signal(_signal(0, 5, close=90.0))
    assert exe.trades[0].pnl_quote == pytest.approx(-10.0)
    assert exe.realized_pnl() == pytest.approx(-10.0)
