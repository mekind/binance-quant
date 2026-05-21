"""Smoke tests for Stage 2 strategies. No network."""

import numpy as np
import pandas as pd
import pytest

from money_maker.backtest.engine import run_backtest
from money_maker.strategies import registry
from money_maker.strategies.bbands_atr import BBandsAtr, _atr
from money_maker.strategies.rsi_mr import RsiMeanReversion, _rsi
from money_maker.strategies.vol_breakout import VolBreakout


def _synthetic_ohlcv(n: int = 800, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0002, 0.004, n)
    close = 30_000 * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.0025, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.0025, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="1min", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.uniform(1, 10, n)},
        index=idx,
    )


@pytest.mark.parametrize("name", registry.list_names())
def test_every_strategy_produces_valid_signals(name):
    df = _synthetic_ohlcv()
    strat = registry.build(name)
    sig = strat.signals(df)

    assert len(sig) == len(df)
    assert sig.index.equals(df.index)
    assert sig.isin([0, 1]).all(), f"{name} produced non-binary signals"


@pytest.mark.parametrize("name", registry.list_names())
def test_every_strategy_backtests_cleanly(name):
    df = _synthetic_ohlcv()
    sig = registry.build(name).signals(df)
    r = run_backtest(df, sig, fee=0.001)
    assert len(r.equity) == len(df)
    assert -1.0 < r.max_drawdown <= 0.0
    assert r.trades >= 0


def test_vol_breakout_rejects_bad_params():
    with pytest.raises(ValueError):
        VolBreakout(lookback=1)
    with pytest.raises(ValueError):
        VolBreakout(k=0)


def test_rsi_mr_rejects_bad_thresholds():
    with pytest.raises(ValueError):
        RsiMeanReversion(oversold=70, exit_level=30)
    with pytest.raises(ValueError):
        RsiMeanReversion(oversold=-5)


def test_rsi_bounds():
    close = pd.Series(np.linspace(100, 200, 200))
    rsi = _rsi(close, period=14)
    assert (rsi.between(0, 100)).all()


def test_rsi_mr_state_machine():
    # Construct a series that dips low (oversold) then rises high (exit)
    idx = pd.date_range("2025-01-01", periods=100, freq="1min", tz="UTC")
    close = pd.Series(
        np.concatenate([np.linspace(100, 60, 50), np.linspace(60, 140, 50)]),
        index=idx,
    )
    df = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close,
        "volume": 1.0,
    }, index=idx)

    sig = RsiMeanReversion(period=14, oversold=30, exit_level=55).signals(df)
    # Should enter long during the dip and exit by the end of the rally
    assert sig.sum() > 0
    assert sig.iloc[-1] == 0


def test_registry_unknown_raises():
    with pytest.raises(KeyError):
        registry.build("does_not_exist")


def test_bbands_atr_rejects_bad_params():
    with pytest.raises(ValueError):
        BBandsAtr(period=1)
    with pytest.raises(ValueError):
        BBandsAtr(n_std=0)
    with pytest.raises(ValueError):
        BBandsAtr(atr_period=1)
    with pytest.raises(ValueError):
        BBandsAtr(atr_mult=0)


def test_atr_positive_and_aligned():
    df = _synthetic_ohlcv(n=300)
    atr = _atr(df, period=14)
    assert len(atr) == len(df)
    assert (atr.dropna() >= 0).all()


def test_bbands_atr_enters_on_dip_and_stop_exits_on_crash():
    # Build a series that dips below the lower band then crashes through the stop.
    idx = pd.date_range("2025-01-01", periods=120, freq="1min", tz="UTC")
    close = np.concatenate([
        np.full(40, 100.0),                      # flat → bands tight
        np.linspace(100.0, 80.0, 20),            # dip → trigger entry
        np.full(10, 80.0),                       # hold
        np.linspace(80.0, 40.0, 30),             # crash → stop must fire
        np.full(20, 40.0),
    ])
    df = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close, "volume": 1.0,
    }, index=idx)

    sig = BBandsAtr(period=20, n_std=2.0, atr_period=14, atr_mult=2.0).signals(df)
    assert sig.sum() > 0, "should have entered during the dip"
    assert sig.iloc[-1] == 0, "stop or mean-revert must have flattened by the end"
