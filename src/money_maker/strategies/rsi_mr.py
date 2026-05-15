"""RSI mean reversion — long when oversold, exit when neutral.

Single state-machine signal:
  - flat → long when RSI crosses below `oversold`
  - long → flat when RSI crosses above `exit_level`

We avoid `ffill`-style hysteresis bugs by computing positions iteratively.
For 100k-bar series this loop is still <100ms.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # Wilder smoothing ≈ EMA with alpha = 1/period
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


class RsiMeanReversion(Strategy):
    name = "rsi_mr"

    def __init__(self, period: int = 14, oversold: float = 30.0, exit_level: float = 55.0):
        if not (0 < oversold < exit_level < 100):
            raise ValueError("require 0 < oversold < exit_level < 100")
        self.period = period
        self.oversold = oversold
        self.exit_level = exit_level

    def signals(self, df: pd.DataFrame) -> pd.Series:
        rsi = _rsi(df["close"], self.period)
        pos = np.zeros(len(rsi), dtype=np.int8)
        state = 0
        for i, v in enumerate(rsi.to_numpy()):
            if state == 0 and v < self.oversold:
                state = 1
            elif state == 1 and v > self.exit_level:
                state = 0
            pos[i] = state
        return pd.Series(pos, index=df.index, name="signal")
