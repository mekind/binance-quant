"""Classic EMA crossover — long when fast EMA > slow EMA, flat otherwise.

Long-only because we're trading spot. Simple, transparent baseline.
"""

from __future__ import annotations

import pandas as pd

from .base import Strategy


class EmaCross(Strategy):
    name = "ema_cross"

    def __init__(self, fast: int = 12, slow: int = 26):
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.fast = fast
        self.slow = slow

    def signals(self, df: pd.DataFrame) -> pd.Series:
        fast = df["close"].ewm(span=self.fast, adjust=False).mean()
        slow = df["close"].ewm(span=self.slow, adjust=False).mean()
        return (fast > slow).astype(int)
