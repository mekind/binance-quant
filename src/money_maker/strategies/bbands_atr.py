"""Bollinger band mean-reversion with ATR-based stop loss.

Entry:  close pierces the lower band (oversold) → long.
Exit:   close crosses back above the middle band (mean reverted) → flat,
        OR the bar's low falls below entry_price - atr_mult * ATR(at_entry) → stop.

Stops are evaluated against the current bar's low to detect intra-bar trips;
the position is then flat for the *next* bar, consistent with how the
backtester executes at next-bar open. This understates real stop fills (we
escape at next open instead of at the stop level), so reported PnL is a
conservative-on-the-upside / pessimistic-on-fills approximation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import Strategy


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


class BBandsAtr(Strategy):
    name = "bbands_atr"

    def __init__(
        self,
        period: int = 20,
        n_std: float = 2.0,
        atr_period: int = 14,
        atr_mult: float = 2.0,
    ):
        if period < 2:
            raise ValueError("period must be >= 2")
        if n_std <= 0:
            raise ValueError("n_std must be > 0")
        if atr_period < 2:
            raise ValueError("atr_period must be >= 2")
        if atr_mult <= 0:
            raise ValueError("atr_mult must be > 0")
        self.period = period
        self.n_std = n_std
        self.atr_period = atr_period
        self.atr_mult = atr_mult

    def signals(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        mid = close.rolling(self.period).mean()
        std = close.rolling(self.period).std(ddof=0)
        lower = mid - self.n_std * std
        atr = _atr(df, self.atr_period)

        close_a = close.to_numpy()
        low_a = df["low"].to_numpy()
        mid_a = mid.to_numpy()
        lower_a = lower.to_numpy()
        atr_a = atr.to_numpy()

        pos = np.zeros(len(df), dtype=np.int8)
        state = 0
        stop = np.nan
        for i in range(len(df)):
            if state == 0:
                if (
                    np.isfinite(lower_a[i])
                    and np.isfinite(atr_a[i])
                    and close_a[i] < lower_a[i]
                ):
                    state = 1
                    stop = close_a[i] - self.atr_mult * atr_a[i]
            elif state == 1 and (low_a[i] < stop or close_a[i] > mid_a[i]):
                state = 0
                stop = np.nan
            pos[i] = state
        return pd.Series(pos, index=df.index, name="signal")
