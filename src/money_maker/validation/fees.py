"""Fee sensitivity sweep.

A strategy that's profitable at 0.05% but underwater at 0.15% can't survive
real Binance taker fees (currently 0.10% spot, lower with BNB discount).
This sweep should be applied to ANY candidate strategy before paper trading.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd

from money_maker.backtest.engine import run_backtest
from money_maker.strategies import registry


def fee_sweep(
    df: pd.DataFrame,
    strategy: str,
    fees: Iterable[float] = (0.0005, 0.00075, 0.001, 0.00125, 0.0015, 0.002),
    params: Mapping | None = None,
) -> pd.DataFrame:
    """Return one row per fee level with the full metric set."""
    strat_factory = lambda: registry.build(strategy, **(params or {}))  # noqa: E731
    sig = strat_factory().signals(df)
    rows: list[dict] = []
    for fee in fees:
        r = run_backtest(df, sig, fee=fee)
        rows.append({
            "fee": fee,
            "trades": r.trades,
            "total_return": r.total_return,
            "sharpe": r.sharpe,
            "max_drawdown": r.max_drawdown,
            "win_rate": r.win_rate,
        })
    return pd.DataFrame(rows)
