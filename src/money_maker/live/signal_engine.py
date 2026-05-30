"""Translate a live kline stream into position-change events.

Responsibilities:
  - Buffer the last N closed bars as a DataFrame compatible with the
    backtest Strategy interface (same columns, same dtype).
  - On every *closed* bar, re-run `strategy.signals(df)` and read the last
    value as the desired position.
  - Emit a `SignalEvent` only when desired position differs from the last
    emitted one, so downstream executors stay idempotent.

We re-run the full strategy each bar instead of caching state, because not
every Strategy in the registry is incremental. The buffer cap keeps the
recompute cost bounded.

Assumes we start flat. For real trading the executor would need to
reconcile against actual account state at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from money_maker.strategies.base import Strategy

from .events import KlineEvent


@dataclass(frozen=True, slots=True)
class SignalEvent:
    timestamp: datetime
    symbol: str
    desired_position: int  # {0, 1}
    last_close: float


class SignalEngine:
    def __init__(self, strategy: Strategy, max_bars: int = 1000, warmup_bars: int = 50):
        if max_bars < 2:
            raise ValueError("max_bars must be >= 2")
        if warmup_bars < 1:
            raise ValueError("warmup_bars must be >= 1")
        self.strategy = strategy
        self.max_bars = max_bars
        self.warmup_bars = warmup_bars
        self._bars: list[dict] = []
        self._last_position: int = 0

    @property
    def last_position(self) -> int:
        return self._last_position

    @property
    def n_bars(self) -> int:
        return len(self._bars)

    def seed(self, df: pd.DataFrame) -> None:
        """Preload historical bars so warmup is satisfied without waiting live."""
        rows = df.tail(self.max_bars)
        self._bars = [
            {
                "open_time": ts,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for ts, row in zip(rows.index, rows.itertuples(index=False), strict=True)
        ]

    def on_kline(self, event: KlineEvent) -> SignalEvent | None:
        if not event.is_closed:
            return None
        self._bars.append({
            "open_time": event.open_time,
            "open": event.open,
            "high": event.high,
            "low": event.low,
            "close": event.close,
            "volume": event.volume,
        })
        if len(self._bars) > self.max_bars:
            self._bars = self._bars[-self.max_bars :]
        if len(self._bars) < self.warmup_bars:
            return None

        df = pd.DataFrame(self._bars).set_index("open_time")
        sig = self.strategy.signals(df)
        desired = int(sig.iloc[-1])
        if desired == self._last_position:
            return None

        self._last_position = desired
        return SignalEvent(
            timestamp=event.close_time,
            symbol=event.symbol,
            desired_position=desired,
            last_close=event.close,
        )
