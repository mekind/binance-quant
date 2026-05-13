"""Typer CLI: `mm download`, `mm backtest`."""

from __future__ import annotations

from datetime import datetime, timezone

import typer
from loguru import logger
from rich.console import Console

from money_maker.backtest.engine import run_backtest
from money_maker.config import settings
from money_maker.data.downloader import download_klines, load_klines
from money_maker.strategies.ema_cross import EmaCross

app = typer.Typer(help="Binance spot quant trading toolkit")
console = Console()


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
    symbol: str = typer.Option(None),
    interval: str = typer.Option(None),
    fast: int = typer.Option(12),
    slow: int = typer.Option(26),
    fee: float = typer.Option(0.001, help="Per-side fee, default 0.1% taker"),
):
    """Run the EMA-cross strategy against downloaded data."""
    symbol = symbol or settings.default_symbol
    interval = interval or settings.default_interval

    df = load_klines(symbol, interval)
    strat = EmaCross(fast=fast, slow=slow)
    sig = strat.signals(df)
    result = run_backtest(df, sig, fee=fee)

    console.print(f"[bold]{strat.name}[/bold] on {symbol} {interval}")
    console.print(f"  bars: {len(df):,}  range: {df.index[0]} → {df.index[-1]}")
    console.print(f"  {result.summary()}")


@app.command()
def info():
    """Print loaded settings (without leaking secrets)."""
    masked_key = (settings.binance_api_key[:4] + "…") if settings.binance_api_key else "(unset)"
    console.print({
        "testnet": settings.binance_testnet,
        "api_key": masked_key,
        "default_symbol": settings.default_symbol,
        "default_interval": settings.default_interval,
        "max_position_usdt": settings.max_position_usdt,
    })


if __name__ == "__main__":
    logger.remove()
    logger.add(lambda m: console.print(m, end=""), level="INFO")
    app()
