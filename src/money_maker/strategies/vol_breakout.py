"""Larry Williams volatility breakout.

Idea: today's range tends to mean-revert. If price moves >k * yesterday's range
above today's open, the move is statistically unusual — ride the breakout.

For intraday bars we generalize "today" → rolling window of `lookback` bars.
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy


class VolBreakout(Strategy):
    name = "vol_breakout"

    def __init__(self, lookback: int = 20, k: float = 0.5):
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        if k <= 0:
            raise ValueError("k must be > 0")
        self.lookback = lookback
        self.k = k

    def signals(self, df: pd.DataFrame) -> pd.Series:
        # Average range over the previous `lookback` bars (excludes current bar)
        prev_range = (df["high"] - df["low"]).shift(1).rolling(self.lookback).mean()
        breakout_price = df["open"] + self.k * prev_range
        # Enter long if bar's high pierces the breakout level
        return (df["high"] > breakout_price).astype(int).fillna(0)
