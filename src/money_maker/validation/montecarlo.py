"""Monte Carlo trade-order shuffle.

Given an actual backtest's per-bar net returns, shuffle the order N times and
recompute equity. The realized order produces one Sharpe and one max
drawdown; the shuffle distribution tells us whether those values are *typical*
or *exceptional* for this set of returns.

Useful signal: if the realized MDD sits at the 1st percentile of shuffled
MDDs, the actual sequence was unusually painful (a clustered losing streak)
— possibly a hint the strategy correlates with regime, not random.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def montecarlo_shuffle(
    returns: pd.Series,
    n_iters: int = 1000,
    seed: int = 0,
) -> dict:
    """Return shuffle-distribution stats for `returns`.

    Output dict has:
      observed_sharpe, observed_mdd, observed_total
      sharpe_p05/p50/p95, mdd_p05/p50/p95, total_p05/p50/p95
      sharpe_percentile, mdd_percentile  (realized rank within shuffle dist)
    """
    if n_iters < 10:
        raise ValueError("n_iters must be >= 10")
    arr = returns.to_numpy(dtype=float)
    if arr.size == 0:
        raise ValueError("returns is empty")

    def _stats(r: np.ndarray) -> tuple[float, float, float]:
        std = r.std(ddof=0)
        sharpe = (r.mean() / std) if std > 0 else 0.0
        eq = np.cumprod(1.0 + r)
        mdd = (eq / np.maximum.accumulate(eq) - 1.0).min()
        total = eq[-1] - 1.0
        return float(sharpe), float(mdd), float(total)

    obs_sharpe, obs_mdd, obs_total = _stats(arr)

    rng = np.random.default_rng(seed)
    sh = np.empty(n_iters)
    md = np.empty(n_iters)
    tt = np.empty(n_iters)
    for i in range(n_iters):
        shuffled = rng.permutation(arr)
        sh[i], md[i], tt[i] = _stats(shuffled)

    return {
        "observed_sharpe": obs_sharpe,
        "observed_mdd": obs_mdd,
        "observed_total": obs_total,
        "sharpe_p05": float(np.percentile(sh, 5)),
        "sharpe_p50": float(np.percentile(sh, 50)),
        "sharpe_p95": float(np.percentile(sh, 95)),
        "mdd_p05": float(np.percentile(md, 5)),
        "mdd_p50": float(np.percentile(md, 50)),
        "mdd_p95": float(np.percentile(md, 95)),
        "total_p05": float(np.percentile(tt, 5)),
        "total_p50": float(np.percentile(tt, 50)),
        "total_p95": float(np.percentile(tt, 95)),
        # Fraction of shuffles WORSE than observed (higher = realized was better)
        "sharpe_percentile": float((sh < obs_sharpe).mean()),
        "mdd_percentile": float((md < obs_mdd).mean()),
    }
