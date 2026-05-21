"""Stage 3 robustness tests — synthetic data only."""

import numpy as np
import pandas as pd
import pytest

from money_maker.backtest.engine import run_backtest
from money_maker.strategies import registry
from money_maker.validation import (
    fee_sweep,
    grid_search,
    montecarlo_shuffle,
    walk_forward,
)


def _synthetic_ohlcv(n: int = 1500, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0003, 0.005, n)
    close = 30_000 * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.uniform(1, 10, n)},
        index=idx,
    )


def test_grid_search_runs_and_skips_invalid():
    df = _synthetic_ohlcv(n=500)
    # Some combinations have fast>=slow → should be skipped, not crash
    g = {"fast": [5, 10, 30], "slow": [10, 20, 50]}
    result = grid_search(df, "ema_cross", g)
    assert not result.empty
    assert {"fast", "slow", "sharpe", "max_drawdown"}.issubset(result.columns)
    # All surviving rows must respect fast < slow
    assert (result["fast"] < result["slow"]).all()


def test_walkforward_with_grid_produces_oos_rows():
    df = _synthetic_ohlcv(n=1500)
    result = walk_forward(
        df, "ema_cross",
        train_bars=400, test_bars=200,
        grid={"fast": [5, 10], "slow": [20, 40]},
    )
    assert len(result) >= 3
    assert (result["train_end"] < result["test_start"]).all()
    assert result["oos_trades"].sum() >= 0


def test_walkforward_with_fixed_params():
    df = _synthetic_ohlcv(n=1200)
    result = walk_forward(
        df, "ema_cross",
        train_bars=300, test_bars=200,
        fixed_params={"fast": 5, "slow": 20},
    )
    assert len(result) >= 3
    # Fixed params → every window's params dict is identical
    assert all(row == {"fast": 5, "slow": 20} for row in result["params"])


def test_walkforward_validates_args():
    df = _synthetic_ohlcv(n=100)
    with pytest.raises(ValueError):
        walk_forward(df, "ema_cross", train_bars=0, test_bars=10)
    with pytest.raises(ValueError):
        walk_forward(
            df, "ema_cross", train_bars=10, test_bars=10,
            grid={"fast": [5]}, fixed_params={"fast": 5},
        )


def test_montecarlo_distribution_shape():
    df = _synthetic_ohlcv(n=800)
    strat = registry.build("ema_cross")
    r = run_backtest(df, strat.signals(df))
    stats = montecarlo_shuffle(r.returns, n_iters=200, seed=42)

    # Percentile rank lives in [0, 1]
    assert 0.0 <= stats["sharpe_percentile"] <= 1.0
    assert 0.0 <= stats["mdd_percentile"] <= 1.0
    # Ordering of percentiles must hold
    assert stats["sharpe_p05"] <= stats["sharpe_p50"] <= stats["sharpe_p95"]
    assert stats["mdd_p05"] <= stats["mdd_p50"] <= stats["mdd_p95"]


def test_montecarlo_rejects_tiny_iters():
    s = pd.Series([0.01, -0.005, 0.002])
    with pytest.raises(ValueError):
        montecarlo_shuffle(s, n_iters=3)


def test_fee_sweep_monotone_for_active_strategy():
    df = _synthetic_ohlcv(n=600)
    result = fee_sweep(df, "ema_cross", fees=[0.0001, 0.001, 0.005])
    assert len(result) == 3
    # Higher fees can only hurt return for the SAME signal series
    assert (result.sort_values("fee")["total_return"].diff().dropna() <= 1e-12).all()
