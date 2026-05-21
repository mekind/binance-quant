"""Backtest result visualization — equity curve, drawdown, monthly heatmap.

Uses a non-interactive matplotlib backend so the CLI can be run headless. All
figures are saved to disk; nothing is shown on screen.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .engine import BacktestResult


def _equity_curve(result: BacktestResult, ax: plt.Axes, title: str) -> None:
    ax.plot(result.equity.index, result.equity.to_numpy(), color="#1f77b4", linewidth=1.2)
    ax.axhline(1.0, color="gray", linewidth=0.6, linestyle="--")
    ax.set_title(f"Equity curve — {title}")
    ax.set_ylabel("equity (base 1.0)")
    ax.grid(alpha=0.3)


def _drawdown(result: BacktestResult, ax: plt.Axes) -> None:
    dd = result.equity / result.equity.cummax() - 1.0
    ax.fill_between(dd.index, dd.to_numpy(), 0.0, color="#d62728", alpha=0.4)
    ax.set_title(f"Drawdown — max {result.max_drawdown:.2%}")
    ax.set_ylabel("drawdown")
    ax.grid(alpha=0.3)


def _monthly_heatmap(result: BacktestResult, ax: plt.Axes) -> None:
    # Compound per-bar net returns into monthly returns.
    monthly = (1.0 + result.returns).resample("MS").prod() - 1.0
    if monthly.empty:
        ax.set_title("Monthly returns — (no data)")
        ax.axis("off")
        return

    frame = pd.DataFrame({
        "year": monthly.index.year,
        "month": monthly.index.month,
        "ret": monthly.to_numpy(),
    })
    pivot = frame.pivot(index="year", columns="month", values="ret")
    pivot = pivot.reindex(columns=range(1, 13))

    vmax = float(np.nanmax(np.abs(pivot.to_numpy()))) or 1e-9
    im = ax.imshow(
        pivot.to_numpy(),
        aspect="auto",
        cmap="RdYlGn",
        vmin=-vmax,
        vmax=vmax,
    )
    ax.set_xticks(range(12))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_title("Monthly returns")
    for (i, j), v in np.ndenumerate(pivot.to_numpy()):
        if np.isfinite(v):
            ax.text(j, i, f"{v:+.1%}", ha="center", va="center", fontsize=7, color="black")
    plt.colorbar(im, ax=ax, fraction=0.025, pad=0.02)


def save_report(result: BacktestResult, out_dir: str | Path, title: str) -> Path:
    """Render equity / drawdown / monthly heatmap to a single PNG. Returns its path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_title = title.replace(" ", "_").replace("/", "_")
    path = out_dir / f"{safe_title}.png"

    fig, axes = plt.subplots(3, 1, figsize=(11, 11), gridspec_kw={"height_ratios": [2, 1, 2]})
    _equity_curve(result, axes[0], title)
    _drawdown(result, axes[1])
    _monthly_heatmap(result, axes[2])
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
