"""Vectorized event-naive backtester.

Assumptions:
  - Long-only spot. Signal in {0, 1}.
  - Execution at NEXT bar's open (no look-ahead).
  - Fixed taker fee on every entry and exit.
  - No partial fills, no slippage model beyond the fee (extend later).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    equity: pd.Series          # equity curve, base 1.0
    returns: pd.Series         # per-bar net returns
    positions: pd.Series       # realized position each bar (0/1)
    trades: int
    total_return: float
    sharpe: float              # annualized, assuming bars per year inferred
    max_drawdown: float
    win_rate: float

    def summary(self) -> str:
        return (
            f"trades={self.trades}  "
            f"total={self.total_return:+.2%}  "
            f"sharpe={self.sharpe:.2f}  "
            f"mdd={self.max_drawdown:.2%}  "
            f"win={self.win_rate:.2%}"
        )


def _bars_per_year(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 365 * 24 * 60
    median_dt = pd.Series(index).diff().dropna().median()
    seconds = median_dt.total_seconds()
    return (365 * 24 * 3600) / seconds if seconds > 0 else 1.0


def run_backtest(
    df: pd.DataFrame,
    signals: pd.Series,
    fee: float = 0.001,   # Binance spot taker
) -> BacktestResult:
    """Execute signals at next-bar open and compute per-bar net returns."""
    df = df.sort_index()
    signals = signals.reindex(df.index).fillna(0).astype(int).clip(0, 1)

    # Realized position: signal generated at bar t becomes active at bar t+1
    position = signals.shift(1).fillna(0).astype(int)

    # Per-bar return uses open-to-open so the entry/exit at "next open" is consistent
    open_ = df["open"]
    bar_ret = open_.pct_change().shift(-1).fillna(0)
    # bar_ret[t] = (open[t+1] / open[t]) - 1, i.e. the return from holding through bar t.

    gross = position * bar_ret

    # Fee charged on every position change (entry or exit)
    changes = position.diff().abs().fillna(position.iloc[0])
    fee_cost = changes * fee
    net = gross - fee_cost

    equity = (1.0 + net).cumprod()
    drawdown = equity / equity.cummax() - 1.0

    bpy = _bars_per_year(df.index)
    mean, std = net.mean(), net.std(ddof=0)
    sharpe = (mean / std) * np.sqrt(bpy) if std > 0 else 0.0

    # Trades = number of entry events (0 -> 1 transitions)
    entries = ((position == 1) & (position.shift(1).fillna(0) == 0)).sum()

    # Win rate: per closed trade. Group bars into trade segments.
    trade_id = (position.diff().fillna(0) == 1).cumsum() * position
    pnl_per_trade = net.groupby(trade_id).sum().drop(0, errors="ignore")
    win_rate = (pnl_per_trade > 0).mean() if len(pnl_per_trade) else 0.0

    return BacktestResult(
        equity=equity,
        returns=net,
        positions=position,
        trades=int(entries),
        total_return=float(equity.iloc[-1] - 1.0),
        sharpe=float(sharpe),
        max_drawdown=float(drawdown.min()),
        win_rate=float(win_rate),
    )
