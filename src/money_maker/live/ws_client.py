"""Binance kline WebSocket client with auto-reconnect.

The async generator `kline_stream` yields `KlineEvent` (closed *and* in-progress
bars; downstream filters on `is_closed`). On any transient failure it
reconnects with exponential backoff capped at `max_backoff`.

The `connect_fn` parameter is exposed so tests can substitute a fake.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import websockets
from loguru import logger

from .events import KlineEvent

PROD_BASE = "wss://stream.binance.com:9443/ws"
TESTNET_BASE = "wss://stream.testnet.binance.vision/ws"


def stream_url(symbol: str, interval: str, *, testnet: bool) -> str:
    base = TESTNET_BASE if testnet else PROD_BASE
    return f"{base}/{symbol.lower()}@kline_{interval}"


async def kline_stream(
    symbol: str,
    interval: str,
    *,
    testnet: bool = True,
    max_backoff: float = 60.0,
    connect_fn: Callable[[str], Any] | None = None,
) -> AsyncIterator[KlineEvent]:
    """Yield `KlineEvent`s forever. Reconnects on disconnect with backoff."""
    url = stream_url(symbol, interval, testnet=testnet)
    connect = connect_fn or (lambda u: websockets.connect(u, ping_interval=20, ping_timeout=10))
    backoff = 1.0
    while True:
        try:
            async with connect(url) as ws:
                logger.info(f"WS connected → {url}")
                backoff = 1.0
                async for raw in ws:
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning(f"WS non-JSON frame dropped: {raw!r:.80}")
                        continue
                    event = KlineEvent.from_binance(payload)
                    if event is not None:
                        yield event
        except asyncio.CancelledError:
            logger.info("WS stream cancelled")
            raise
        except Exception as e:
            logger.warning(f"WS disconnect ({type(e).__name__}: {e}) — reconnect in {backoff:.1f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
