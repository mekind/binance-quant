"""Stage 4 part 4 tests — runner integration + Binance testnet router."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pandas as pd
import pytest

from money_maker.live.events import KlineEvent
from money_maker.live.paper_executor import PaperExecutor
from money_maker.live.router import SimulatedRouter
from money_maker.live.runner import run_live
from money_maker.live.testnet_router import (
    BinanceTestnetRouter,
    _parse_fills,
    _sign,
)
from money_maker.strategies.base import Strategy

# ─────────────────────────── runner integration ────────────────────────────


class _StepStrategy(Strategy):
    """Long when close > 100, else flat. Deterministic for runner test."""

    name = "step"

    def signals(self, df: pd.DataFrame) -> pd.Series:
        return (df["close"] > 100.0).astype(int)


async def _finite_stream(events: list[KlineEvent]) -> AsyncIterator[KlineEvent]:
    for ev in events:
        yield ev


def _ev(t_min: int, close: float, *, closed: bool = True) -> KlineEvent:
    t = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=t_min)
    return KlineEvent(
        symbol="BTCUSDT", interval="1m",
        open_time=t, close_time=t + timedelta(minutes=1),
        open=close, high=close, low=close, close=close,
        volume=1.0, is_closed=closed,
    )


@pytest.mark.asyncio
async def test_runner_drives_full_pipeline_end_to_end():
    # 5 warmup bars below 100 (flat), then push above 100 (long), then back (flat)
    events = [
        _ev(0, 90.0), _ev(1, 91.0), _ev(2, 92.0), _ev(3, 93.0), _ev(4, 94.0),
        _ev(5, 110.0),   # → desired_position transitions 0 → 1
        _ev(6, 115.0),   # still long, no emit
        _ev(7, 80.0),    # → 1 → 0
    ]
    executor = PaperExecutor(router=SimulatedRouter(), max_position_usdt=100.0)
    await run_live(
        _StepStrategy(), "BTCUSDT", "1m", executor,
        warmup_bars=5, max_bars=100,
        stream=_finite_stream(events),
    )
    assert len(executor.trades) == 1
    trade = executor.trades[0]
    assert trade.entry_price == pytest.approx(110.0)
    assert trade.exit_price == pytest.approx(80.0)
    # Loss: bought at 110, sold at 80, qty = 100/110
    assert trade.pnl_quote == pytest.approx((80.0 - 110.0) * (100.0 / 110.0))


@pytest.mark.asyncio
async def test_runner_ignores_unclosed_bars():
    events = [_ev(i, 95.0 + i, closed=False) for i in range(20)]
    executor = PaperExecutor(router=SimulatedRouter(), max_position_usdt=100.0)
    await run_live(
        _StepStrategy(), "BTCUSDT", "1m", executor,
        warmup_bars=3,
        stream=_finite_stream(events),
    )
    assert executor.trades == []
    assert executor.position == 0


# ──────────────────────── testnet router (mocked) ──────────────────────────


def test_sign_matches_known_vector():
    # HMAC-SHA256 of "symbol=BTCUSDT&side=BUY" with secret "k" — pre-computed.
    import hashlib
    import hmac
    expected = hmac.new(b"k", b"symbol=BTCUSDT&side=BUY", hashlib.sha256).hexdigest()
    assert _sign("k", "symbol=BTCUSDT&side=BUY") == expected


def test_parse_fills_weights_correctly():
    payload = {
        "fills": [
            {"qty": "0.3", "price": "30000.0"},
            {"qty": "0.7", "price": "31000.0"},
        ],
    }
    qty, avg = _parse_fills(payload)
    assert qty == pytest.approx(1.0)
    assert avg == pytest.approx(30_700.0)


def test_testnet_router_requires_keys():
    with pytest.raises(ValueError):
        BinanceTestnetRouter("", "secret")
    with pytest.raises(ValueError):
        BinanceTestnetRouter("key", "")


@pytest.mark.asyncio
async def test_testnet_router_buy_signs_and_parses_response():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "clientOrderId": "abc",
                "executedQty": "1.0",
                "cummulativeQuoteQty": "30700.0",
                "fills": [
                    {"qty": "0.3", "price": "30000.0"},
                    {"qty": "0.7", "price": "31000.0"},
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    router = BinanceTestnetRouter("key", "secret", client=client)
    try:
        order = await router.buy("BTCUSDT", quote_qty=30_700.0, ref_price=30_500.0)
    finally:
        await router.aclose()

    assert order.symbol == "BTCUSDT"
    assert order.side == "BUY"
    assert order.filled_qty == pytest.approx(1.0)
    assert order.avg_price == pytest.approx(30_700.0)
    # Request must have hit the testnet base, carry the API key, and include signature
    assert "testnet.binance.vision" in captured["url"]
    assert captured["headers"]["x-mbx-apikey"] == "key"
    assert "signature=" in captured["url"]
    assert "newOrderRespType=FULL" in captured["url"]


@pytest.mark.asyncio
async def test_testnet_router_raises_on_http_error():
    def handler(_request):
        return httpx.Response(401, json={"code": -2014, "msg": "API-key format invalid"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    router = BinanceTestnetRouter("badkey", "badsecret", client=client)
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await router.buy("BTCUSDT", quote_qty=50.0, ref_price=30_000.0)
    finally:
        await router.aclose()
