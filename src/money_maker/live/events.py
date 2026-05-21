"""Typed events flowing through the live pipeline.

Kept dependency-free so they can be constructed in tests without touching a
WebSocket. All numeric fields are floats — Binance ships them as strings, the
parser is responsible for the conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class KlineEvent:
    symbol: str
    interval: str
    open_time: datetime    # UTC
    close_time: datetime   # UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_closed: bool        # only act on closed bars

    @classmethod
    def from_binance(cls, payload: dict) -> KlineEvent | None:
        """Parse a Binance WS `kline` event. Returns None for non-kline frames."""
        if payload.get("e") != "kline":
            return None
        k = payload["k"]
        return cls(
            symbol=k["s"],
            interval=k["i"],
            open_time=datetime.fromtimestamp(k["t"] / 1000, tz=UTC),
            close_time=datetime.fromtimestamp(k["T"] / 1000, tz=UTC),
            open=float(k["o"]),
            high=float(k["h"]),
            low=float(k["l"]),
            close=float(k["c"]),
            volume=float(k["v"]),
            is_closed=bool(k["x"]),
        )
