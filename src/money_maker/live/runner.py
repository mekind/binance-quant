"""End-to-end live runner: WS feed → SignalEngine → PaperExecutor.

Single async coroutine drives the whole pipeline. Cancellation propagates
cleanly because the WS client's loop awaits a real asyncio.sleep on the
reconnect path and `kline_stream` re-raises CancelledError.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from loguru import logger

from money_maker.strategies.base import Strategy

from .events import KlineEvent
from .paper_executor import PaperExecutor
from .signal_engine import SignalEngine
from .ws_client import kline_stream


async def run_live(
    strategy: Strategy,
    symbol: str,
    interval: str,
    executor: PaperExecutor,
    *,
    testnet: bool = True,
    warmup_bars: int = 50,
    max_bars: int = 1000,
    stream: AsyncIterator[KlineEvent] | None = None,
) -> None:
    """Block until cancelled, processing live klines through the pipeline.

    `stream` lets tests inject a finite event source instead of the real WS.
    """
    engine = SignalEngine(strategy, max_bars=max_bars, warmup_bars=warmup_bars)
    source = stream or kline_stream(symbol, interval, testnet=testnet)

    logger.info(
        f"live runner up: strategy={strategy.name} symbol={symbol} interval={interval} "
        f"testnet={testnet}"
    )
    try:
        async for event in source:
            sig_event = engine.on_kline(event)
            if sig_event is None:
                continue
            await executor.on_signal(sig_event)
    except asyncio.CancelledError:
        logger.info("live runner cancelled")
        raise
