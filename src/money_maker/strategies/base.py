"""Strategy interface: take OHLCV, return position series in {-1, 0, +1}."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def signals(self, df: pd.DataFrame) -> pd.Series:
        """Return a position series aligned to df.index.

        Values: +1 = long, 0 = flat, -1 = short (ignored on spot).
        Signals must be shifted by the strategy if it uses look-ahead-free
        information — the backtester executes at the NEXT bar's open.
        """
