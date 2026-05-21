"""Typer CLI: `mm download`, `mm backtest`, `mm compare`, `mm info`."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from money_maker.backtest.engine import run_backtest
from money_maker.backtest.plots import save_report
from money_maker.config import settings
from money_maker.data.downloader import download_klines, load_klines
from money_maker.strategies import registry
from money_maker.validation import (
    fee_sweep,
    grid_search,
    montecarlo_shuffle,
    walk_forward,
)

app = typer.Typer(help="Binance spot quant trading toolkit")
console = Console()


def _parse_params(raw: str | None) -> dict:
    """`--params 'fast=5,slow=21'` → {'fast': 5, 'slow': 21}. Also accepts JSON."""
    if not raw:
        return {}
    raw = raw.strip()
    if raw.startswith("{"):
        return json.loads(raw)
    out: dict = {}
    for chunk in raw.split(","):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        k, v = k.strip(), v.strip()
        try:
            out[k] = int(v)
        except ValueError:
            try:
                out[k] = float(v)
            except ValueError:
                out[k] = v
    return out


@app.command()
def download(
    symbol: str = typer.Option(None, help="e.g. BTCUSDT"),
    interval: str = typer.Option(None, help="1m,5m,15m,1h,4h,1d"),
    start: str = typer.Option(..., help="ISO date, e.g. 2025-01-01"),
    end: str = typer.Option(None, help="ISO date, default = now"),
):
    """Download historical klines from Binance."""
    symbol = symbol or settings.default_symbol
    interval = interval or settings.default_interval
    end_dt = datetime.fromisoformat(end) if end else datetime.now(tz=timezone.utc)
    path = download_klines(symbol, interval, start, end_dt)
    console.print(f"[green]✓[/green] {path}")


@app.command()
def backtest(
    strategy: str = typer.Option("ema_cross", help=f"One of: {registry.list_names()}"),
    symbol: str = typer.Option(None),
    interval: str = typer.Option(None),
    params: str = typer.Option(None, help="e.g. 'fast=12,slow=26' or JSON"),
    fee: float = typer.Option(0.001, help="Per-side fee, default 0.1% taker"),
    plot_dir: str = typer.Option(None, help="If set, save equity/drawdown/monthly PNG here"),
):
    """Run a strategy against downloaded data."""
    symbol = symbol or settings.default_symbol
    interval = interval or settings.default_interval

    df = load_klines(symbol, interval)
    strat = registry.build(strategy, **_parse_params(params))
    sig = strat.signals(df)
    result = run_backtest(df, sig, fee=fee)

    console.print(f"[bold]{strat.name}[/bold] on {symbol} {interval}")
    console.print(f"  bars: {len(df):,}  range: {df.index[0]} → {df.index[-1]}")
    console.print(f"  {result.summary()}")
    if plot_dir:
        path = save_report(result, plot_dir, title=f"{strat.name}_{symbol}_{interval}")
        console.print(f"  [green]plot[/green] {path}")


@app.command()
def compare(
    symbol: str = typer.Option(None),
    interval: str = typer.Option(None),
    fee: float = typer.Option(0.001),
    plot_dir: str = typer.Option(None, help="If set, save one PNG per strategy here"),
):
    """Run every registered strategy on the same data and tabulate results."""
    symbol = symbol or settings.default_symbol
    interval = interval or settings.default_interval

    df = load_klines(symbol, interval)

    table = Table(title=f"Strategy comparison — {symbol} {interval}")
    for col in ("strategy", "trades", "total", "sharpe", "mdd", "win"):
        table.add_column(col, justify="right" if col != "strategy" else "left")

    for name in registry.list_names():
        strat = registry.build(name)
        sig = strat.signals(df)
        r = run_backtest(df, sig, fee=fee)
        table.add_row(
            name,
            f"{r.trades}",
            f"{r.total_return:+.2%}",
            f"{r.sharpe:.2f}",
            f"{r.max_drawdown:.2%}",
            f"{r.win_rate:.2%}",
        )
        if plot_dir:
            save_report(r, plot_dir, title=f"{name}_{symbol}_{interval}")

    console.print(table)
    if plot_dir:
        console.print(f"  [green]plots saved to[/green] {plot_dir}")


def _parse_grid(raw: str) -> dict[str, list]:
    """`'fast=5,10,20;slow=20,40,80'` → {'fast': [5, 10, 20], 'slow': [20, 40, 80]}."""
    out: dict[str, list] = {}
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, values = chunk.split("=", 1)
        items: list = []
        for v in values.split(","):
            v = v.strip()
            try:
                items.append(int(v))
            except ValueError:
                try:
                    items.append(float(v))
                except ValueError:
                    items.append(v)
        out[key.strip()] = items
    return out


@app.command()
def grid(
    strategy: str = typer.Option(..., help=f"One of: {registry.list_names()}"),
    grid_: str = typer.Option(..., "--grid", help="'fast=5,10,20;slow=30,50,80'"),
    symbol: str = typer.Option(None),
    interval: str = typer.Option(None),
    fee: float = typer.Option(0.001),
    top: int = typer.Option(15, help="Rows to show, sorted by Sharpe"),
):
    """Parameter sensitivity grid search."""
    symbol = symbol or settings.default_symbol
    interval = interval or settings.default_interval
    df = load_klines(symbol, interval)

    g = _parse_grid(grid_)
    result = grid_search(df, strategy, g, fee=fee)
    if result.empty:
        console.print("[yellow]no valid parameter combinations[/yellow]")
        return
    result = result.sort_values("sharpe", ascending=False).head(top)
    console.print(f"[bold]{strategy}[/bold] grid — top {top} by Sharpe")
    console.print(result.to_string(index=False))


@app.command()
def walkforward(
    strategy: str = typer.Option(..., help=f"One of: {registry.list_names()}"),
    train_bars: int = typer.Option(..., help="Bars per train window"),
    test_bars: int = typer.Option(..., help="Bars per test window"),
    grid_: str = typer.Option(None, "--grid", help="Optional grid: 'fast=...;slow=...'"),
    params: str = typer.Option(None, help="Fixed params if no grid"),
    symbol: str = typer.Option(None),
    interval: str = typer.Option(None),
    fee: float = typer.Option(0.001),
):
    """Rolling-window out-of-sample evaluation."""
    symbol = symbol or settings.default_symbol
    interval = interval or settings.default_interval
    df = load_klines(symbol, interval)

    grid_dict = _parse_grid(grid_) if grid_ else None
    fixed = _parse_params(params) if params else None
    result = walk_forward(
        df, strategy, train_bars, test_bars,
        grid=grid_dict, fixed_params=fixed, fee=fee,
    )
    if result.empty:
        console.print("[yellow]not enough data for a single window[/yellow]")
        return
    console.print(f"[bold]{strategy}[/bold] walk-forward — {len(result)} windows")
    summary = result[["window", "train_sharpe", "oos_sharpe", "oos_return", "oos_trades"]]
    console.print(summary.to_string(index=False))
    oos = result["oos_sharpe"]
    console.print(
        f"  OOS Sharpe: mean={oos.mean():.2f}  median={oos.median():.2f}  "
        f"min={oos.min():.2f}  max={oos.max():.2f}  positive={(oos > 0).mean():.0%}"
    )


@app.command()
def mc(
    strategy: str = typer.Option(..., help=f"One of: {registry.list_names()}"),
    iters: int = typer.Option(1000),
    seed: int = typer.Option(0),
    params: str = typer.Option(None),
    symbol: str = typer.Option(None),
    interval: str = typer.Option(None),
    fee: float = typer.Option(0.001),
):
    """Monte Carlo: shuffle realized returns N times, compare observed metrics."""
    symbol = symbol or settings.default_symbol
    interval = interval or settings.default_interval
    df = load_klines(symbol, interval)

    strat = registry.build(strategy, **_parse_params(params))
    r = run_backtest(df, strat.signals(df), fee=fee)
    stats = montecarlo_shuffle(r.returns, n_iters=iters, seed=seed)
    console.print(f"[bold]{strategy}[/bold] Monte Carlo — {iters} shuffles")
    for k, v in stats.items():
        console.print(f"  {k:20s} {v:+.4f}")


@app.command()
def feesweep(
    strategy: str = typer.Option(..., help=f"One of: {registry.list_names()}"),
    params: str = typer.Option(None),
    symbol: str = typer.Option(None),
    interval: str = typer.Option(None),
    fees: str = typer.Option(
        "0.0005,0.00075,0.001,0.00125,0.0015,0.002",
        help="Comma-separated fee levels",
    ),
):
    """Fee sensitivity sweep."""
    symbol = symbol or settings.default_symbol
    interval = interval or settings.default_interval
    df = load_klines(symbol, interval)
    fee_list = [float(x) for x in fees.split(",")]
    result = fee_sweep(df, strategy, fees=fee_list, params=_parse_params(params))
    console.print(f"[bold]{strategy}[/bold] fee sweep")
    console.print(result.to_string(index=False))


@app.command()
def info():
    """Print loaded settings (without leaking secrets) and available strategies."""
    masked_key = (settings.binance_api_key[:4] + "…") if settings.binance_api_key else "(unset)"
    console.print({
        "testnet": settings.binance_testnet,
        "api_key": masked_key,
        "default_symbol": settings.default_symbol,
        "default_interval": settings.default_interval,
        "max_position_usdt": settings.max_position_usdt,
        "strategies": registry.list_names(),
    })


if __name__ == "__main__":
    logger.remove()
    logger.add(lambda m: console.print(m, end=""), level="INFO")
    app()
