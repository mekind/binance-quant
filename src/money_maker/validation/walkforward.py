"""Walk-forward (a.k.a. anchored OOS) evaluation.

For each rolling window we *optionally* pick the best params on the train
segment via grid search, then evaluate those params on the next (untouched)
test segment. The OOS metric distribution is what tells us whether an edge
generalizes. A strategy whose train-Sharpe is great but test-Sharpe is noise
around zero is overfit.

Schema returned (one row per window):
  window, train_start, train_end, test_start, test_end,
  params, train_sharpe, oos_sharpe, oos_return, oos_trades
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from money_maker.backtest.engine import run_backtest
from money_maker.strategies import registry

from .sensitivity import grid_search


def walk_forward(
    df: pd.DataFrame,
    strategy: str,
    train_bars: int,
    test_bars: int,
    grid: Mapping[str, Iterable] | None = None,
    fixed_params: Mapping | None = None,
    fee: float = 0.001,
) -> pd.DataFrame:
    """Rolling-window OOS evaluation.

    If `grid` is given, optimize on each train window and evaluate the winner
    on the next test window. Otherwise use `fixed_params` (or strategy
    defaults) on every test window without any train-side tuning.
    """
    if train_bars <= 0 or test_bars <= 0:
        raise ValueError("train_bars and test_bars must be positive")
    if grid is not None and fixed_params is not None:
        raise ValueError("pass `grid` OR `fixed_params`, not both")

    step = test_bars  # non-overlapping test windows
    rows: list[dict] = []
    n = len(df)
    win = 0
    start = 0
    while start + train_bars + test_bars <= n:
        train = df.iloc[start : start + train_bars]
        test = df.iloc[start + train_bars : start + train_bars + test_bars]

        if grid is not None:
            gs = grid_search(train, strategy, grid, fee=fee)
            if gs.empty:
                start += step
                win += 1
                continue
            best = gs.sort_values("sharpe", ascending=False).iloc[0]
            param_keys = [k for k in gs.columns if k in grid]
            params = {k: best[k] for k in param_keys}
            # Restore native int/float from numpy scalars where possible
            params = {k: (int(v) if float(v).is_integer() else float(v))
                      if hasattr(v, "item") else v for k, v in params.items()}
            train_sharpe = float(best["sharpe"])
        else:
            params = dict(fixed_params or {})
            train_strat = registry.build(strategy, **params)
            train_r = run_backtest(train, train_strat.signals(train), fee=fee)
            train_sharpe = train_r.sharpe

        test_strat = registry.build(strategy, **params)
        r = run_backtest(test, test_strat.signals(test), fee=fee)

        rows.append({
            "window": win,
            "train_start": train.index[0],
            "train_end": train.index[-1],
            "test_start": test.index[0],
            "test_end": test.index[-1],
            "params": params,
            "train_sharpe": train_sharpe,
            "oos_sharpe": r.sharpe,
            "oos_return": r.total_return,
            "oos_trades": r.trades,
        })
        start += step
        win += 1
    return pd.DataFrame(rows)
