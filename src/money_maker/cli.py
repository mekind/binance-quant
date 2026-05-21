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
