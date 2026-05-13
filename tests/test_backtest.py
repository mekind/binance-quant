"""Smoke tests with synthetic data — no network required."""

import numpy as np
import pandas as pd

from money_maker.backtest.engine import run_backtest
from money_maker.strategies.ema_cross import EmaCross


def _synthetic_ohlcv(n: int = 500, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Geometric Brownian-ish walk with slight upward drift
    returns = rng.normal(0.0003, 0.005, n)
    close = 30_000 * np.exp(np.cumsum(returns))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.uniform(1, 10, n)},
        index=idx,
    )


def test_ema_cross_runs_and_produces_valid_result():
    df = _synthetic_ohlcv()
    sig = EmaCross(fast=5, slow=20).signals(df)
    assert sig.isin([0, 1]).all()

    result = run_backtest(df, sig, fee=0.001)
    assert len(result.equity) == len(df)
    assert result.equity.iloc[0] >= 0.95  # nothing weird at start
    assert -1.0 < result.max_drawdown <= 0.0
    assert result.trades >= 0


def test_zero_signal_is_flat():
    df = _synthetic_ohlcv()
    sig = pd.Series(0, index=df.index)
    result = run_backtest(df, sig)
    assert result.trades == 0
    assert abs(result.total_return) < 1e-9
