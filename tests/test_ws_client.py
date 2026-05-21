"""WS client tests — fully mocked, no network."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from money_maker.live.events import KlineEvent
from money_maker.live.ws_client import kline_stream, stream_url


def _binance_kline_frame(close_price: str = "30100.0", is_closed: bool = True) -> str:
    return json.dumps({
        "e": "kline",
        "E": 1_700_000_000_000,
        "s": "BTCUSDT",
        "k": {
            "t": 1_700_000_000_000,
            "T": 1_700_000_059_999,
            "s": "BTCUSDT",
            "i": "1m",
            "o": "30000.0",
            "c": close_price,
            "h": "30200.0",
            "l": "29950.0",
            "v": "12.3",
            "x": is_closed,
        },
    })


def test_stream_url_testnet_vs_prod():
    assert "testnet" in stream_url("BTCUSDT", "1m", testnet=True)
    assert "testnet" not in stream_url("BTCUSDT", "1m", testnet=False)
    assert stream_url("BTCUSDT", "1m", testnet=True).endswith("btcusdt@kline_1m")


def test_kline_event_parses_binance_payload():
    payload = json.loads(_binance_kline_frame(close_price="30150.5", is_closed=False))
    ev = KlineEvent.from_binance(payload)
    assert ev is not None
    assert ev.symbol == "BTCUSDT"
    assert ev.interval == "1m"
    assert ev.close == 30150.5
    assert ev.is_closed is False
    assert ev.open_time.tzinfo is not None


def test_kline_event_ignores_non_kline_frames():
    assert KlineEvent.from_binance({"e": "trade"}) is None
    assert KlineEvent.from_binance({}) is None


class _FakeWs:
    """Async-iterable fake replacement for a websocket connection."""

    def __init__(self, frames: list[str], close_after: bool = True):
        self._frames = list(frames)
        self._close_after = close_after

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __aiter__(self):
        return self._iter()

    async def _iter(self) -> AsyncIterator[str]:
        for f in self._frames:
            yield f
        if self._close_after:
            raise ConnectionError("simulated disconnect")


@pytest.mark.asyncio
async def test_kline_stream_yields_parsed_events():
    frames = [_binance_kline_frame(), _binance_kline_frame(close_price="30200.0")]

    def fake_connect(_url):
        return _FakeWs(frames, close_after=False)

    # Read two events then break.
    events: list[KlineEvent] = []
    agen = kline_stream("BTCUSDT", "1m", connect_fn=fake_connect)
    async for ev in agen:
        events.append(ev)
        if len(events) == 2:
            break
    await agen.aclose()

    assert len(events) == 2
    assert events[0].close == 30100.0
    assert events[1].close == 30200.0


@pytest.mark.asyncio
async def test_kline_stream_reconnects_on_disconnect(monkeypatch):
    # Two connections in a row — first closes, second yields one event.
    calls = {"n": 0}

    def fake_connect(_url):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeWs([_binance_kline_frame()], close_after=True)
        return _FakeWs([_binance_kline_frame(close_price="40000.0")], close_after=False)

    # Skip the backoff sleep so the test is instant.
    async def _no_sleep(_):
        return None
    monkeypatch.setattr("money_maker.live.ws_client.asyncio.sleep", _no_sleep)

    events: list[KlineEvent] = []
    agen = kline_stream("BTCUSDT", "1m", connect_fn=fake_connect)
    async for ev in agen:
        events.append(ev)
        if len(events) == 2:
            break
    await agen.aclose()

    assert calls["n"] == 2, "should have reconnected once"
    assert events[0].close == 30100.0
    assert events[1].close == 40000.0


@pytest.mark.asyncio
async def test_kline_stream_drops_non_json_frames(monkeypatch):
    frames = ["not-json", _binance_kline_frame(close_price="31000.0")]

    def fake_connect(_url):
        return _FakeWs(frames, close_after=False)

    async def _no_sleep(_):
        return None
    monkeypatch.setattr("money_maker.live.ws_client.asyncio.sleep", _no_sleep)

    events: list[KlineEvent] = []
    agen = kline_stream("BTCUSDT", "1m", connect_fn=fake_connect)
    async for ev in agen:
        events.append(ev)
        break
    await agen.aclose()

    assert len(events) == 1
    assert events[0].close == 31000.0
