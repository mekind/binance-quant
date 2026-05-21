"""SignalEngine tests — fully synthetic, no network."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from money_maker.live.events import KlineEvent
from money_maker.live.signal_engine import SignalEngine
from money_maker.strategies.base import Strategy


class _ConstantStrategy(Strategy):
    """Returns a configurable position; useful for transition tests."""

    name = "constant"

    def __init__(self, value: int = 0):
        self.value = value

    def signals(self, df):
        return pd.Series(self.value, index=df.index, dtype=int)


class _ThresholdStrategy(Strategy):
    """Long when close > threshold, flat otherwise. Look-back-free."""

    name = "threshold"

    def __init__(self, threshold: float):
        self.threshold = threshold

    def signals(self, df):
        return (df["close"] > self.threshold).astype(int)


def _make_event(t: datetime, close: float, *, is_closed: bool = True) -> KlineEvent:
    return KlineEvent(
        symbol="BTCUSDT",
        interval="1m",
        open_time=t,
        close_time=t + timedelta(minutes=1),
        open=close, high=close, low=close, close=close,
        volume=1.0, is_closed=is_closed,
    )


def test_engine_rejects_bad_args():
    with pytest.raises(ValueError):
        SignalEngine(_ConstantStrategy(), max_bars=1)
    with pytest.raises(ValueError):
        SignalEngine(_ConstantStrategy(), warmup_bars=0)


def test_engine_ignores_unclosed_bars():
    eng = SignalEngine(_ConstantStrategy(1), warmup_bars=1)
    ev = _make_event(datetime(2025, 1, 1, tzinfo=UTC), 100.0, is_closed=False)
    assert eng.on_kline(ev) is None
    assert eng.n_bars == 0


def test_engine_waits_for_warmup():
    eng = SignalEngine(_ConstantStrategy(1), warmup_bars=3)
    t0 = datetime(2025, 1, 1, tzinfo=UTC)
    # First two bars: warmup not yet satisfied → no emit
    assert eng.on_kline(_make_event(t0, 100.0)) is None
    assert eng.on_kline(_make_event(t0 + timedelta(minutes=1), 100.0)) is None
    # Third bar: now warmup is satisfied AND desired (=1) != last (=0)
    ev = eng.on_kline(_make_event(t0 + timedelta(minutes=2), 100.0))
    assert ev is not None
    assert ev.desired_position == 1


def test_engine_emits_only_on_position_change():
    eng = SignalEngine(_ThresholdStrategy(threshold=100.0), warmup_bars=1)
    t0 = datetime(2025, 1, 1, tzinfo=UTC)
    # close=99 → desired 0, last=0 → no emit
    assert eng.on_kline(_make_event(t0, 99.0)) is None
    # close=101 → desired 1, last=0 → emit
    e1 = eng.on_kline(_make_event(t0 + timedelta(minutes=1), 101.0))
    assert e1 is not None and e1.desired_position == 1
    # close=102 → still 1 → no emit
    assert eng.on_kline(_make_event(t0 + timedelta(minutes=2), 102.0)) is None
    # close=50 → 0, change → emit
    e2 = eng.on_kline(_make_event(t0 + timedelta(minutes=3), 50.0))
    assert e2 is not None and e2.desired_position == 0


def test_engine_seed_satisfies_warmup_immediately():
    idx = pd.date_range("2025-01-01", periods=10, freq="1min", tz="UTC")
    seed_df = pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0},
        index=idx,
    )
    eng = SignalEngine(_ThresholdStrategy(threshold=50.0), warmup_bars=5)
    eng.seed(seed_df)
    assert eng.n_bars == 10

    # Next live bar should emit immediately (warmup already met, position changes)
    ev = eng.on_kline(_make_event(idx[-1] + timedelta(minutes=1), 200.0))
    assert ev is not None
    assert ev.desired_position == 1


def test_engine_caps_buffer_at_max_bars():
    eng = SignalEngine(_ConstantStrategy(0), max_bars=20, warmup_bars=1)
    t0 = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(50):
        eng.on_kline(_make_event(t0 + timedelta(minutes=i), 100.0 + i))
    assert eng.n_bars == 20
    # The retained bars must be the most recent ones
    last_closes = [b["close"] for b in eng._bars]
    assert last_closes[-1] == pytest.approx(100.0 + 49)
    assert last_closes[0] == pytest.approx(100.0 + 30)


def test_engine_integrates_with_real_strategy():
    """Smoke test against the actual EMA-cross strategy from the registry."""
    from money_maker.strategies.ema_cross import EmaCross

    eng = SignalEngine(EmaCross(fast=5, slow=20), warmup_bars=30)
    t0 = datetime(2025, 1, 1, tzinfo=UTC)
    rng = np.random.default_rng(0)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.001, 0.01, 200)))
    last_seen = 0
    transitions = 0
    for i, c in enumerate(closes):
        ev = eng.on_kline(_make_event(t0 + timedelta(minutes=i), float(c)))
        if ev is not None:
            assert ev.desired_position in (0, 1)
            assert ev.desired_position != last_seen
            last_seen = ev.desired_position
            transitions += 1
    # On a random walk we expect at least *some* crossover transitions
    assert transitions >= 1
