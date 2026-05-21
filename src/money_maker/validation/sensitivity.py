"""Parameter sensitivity via exhaustive grid search.

We don't trust a single optimal point — what we want is the *distribution* of
metrics across neighboring parameter combinations. A strategy whose Sharpe
collapses one grid step away from the maximum is curve-fit, not edge.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from itertools import product

import pandas as pd

from money_maker.backtest.engine import run_backtest
from money_maker.strategies import registry


def grid_search(
    df: pd.DataFrame,
    strategy: str,
    grid: Mapping[str, Iterable],
    fee: float = 0.001,
) -> pd.DataFrame:
    """Run every combination from `grid` against `df` and return metrics.

    `grid` example: `{"fast": [5, 10, 20], "slow": [30, 50, 80]}`. Combinations
    that fail to build (e.g. EmaCross requires fast<slow) are skipped silently.
    """
    keys = list(grid.keys())
    values = [list(v) for v in grid.values()]
    rows: list[dict] = []
    for combo in product(*values):
        params = dict(zip(keys, combo, strict=True))
        try:
            strat = registry.build(strategy, **params)
        except (ValueError, TypeError):
            continue
        sig = strat.signals(df)
        r = run_backtest(df, sig, fee=fee)
        rows.append({
            **params,
            "trades": r.trades,
            "total_return": r.total_return,
            "sharpe": r.sharpe,
            "max_drawdown": r.max_drawdown,
            "win_rate": r.win_rate,
        })
    return pd.DataFrame(rows)
