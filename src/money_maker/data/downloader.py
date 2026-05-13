"""Download Binance spot klines (candles) and store as Parquet.

Uses the public REST endpoint (no API key required for market data).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from money_maker.config import DATA_RAW

BINANCE_REST = "https://api.binance.com"
KLINES_PATH = "/api/v3/klines"
MAX_LIMIT = 1000  # Binance hard cap per request

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 3 * 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "30m": 30 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
}

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def _fetch_chunk(client: httpx.Client, symbol: str, interval: str,
                 start_ms: int, end_ms: int) -> list[list]:
    resp = client.get(
        BINANCE_REST + KLINES_PATH,
        params={
            "symbol": symbol,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": MAX_LIMIT,
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _to_ms(dt: datetime | str) -> int:
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def download_klines(
    symbol: str,
    interval: str,
    start: datetime | str,
    end: datetime | str | None = None,
    out_dir: Path = DATA_RAW,
) -> Path:
    """Download candles for [start, end] and write to data/raw/{symbol}_{interval}.parquet."""
    if interval not in INTERVAL_MS:
        raise ValueError(f"Unsupported interval: {interval}")

    start_ms = _to_ms(start)
    end_ms = _to_ms(end) if end else int(time.time() * 1000)
    step = INTERVAL_MS[interval] * MAX_LIMIT

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{symbol}_{interval}.parquet"

    rows: list[list] = []
    cursor = start_ms
    with httpx.Client() as client:
        while cursor < end_ms:
            chunk_end = min(cursor + step, end_ms)
            logger.info(
                f"Fetch {symbol} {interval} "
                f"{datetime.fromtimestamp(cursor / 1000, tz=timezone.utc):%Y-%m-%d %H:%M}"
            )
            chunk = _fetch_chunk(client, symbol, interval, cursor, chunk_end)
            if not chunk:
                break
            rows.extend(chunk)
            cursor = chunk[-1][0] + INTERVAL_MS[interval]
            time.sleep(0.25)  # gentle rate limiting

    if not rows:
        raise RuntimeError("No klines returned — check symbol/interval/dates")

    df = pd.DataFrame(rows, columns=KLINE_COLS)
    numeric = ["open", "high", "low", "close", "volume",
               "quote_volume", "taker_buy_base", "taker_buy_quote"]
    df[numeric] = df[numeric].astype(float)
    df["trades"] = df["trades"].astype(int)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df = df.drop(columns=["ignore"]).drop_duplicates("open_time").set_index("open_time")

    df.to_parquet(out_path)
    logger.success(f"Saved {len(df):,} rows → {out_path}")
    return out_path


def load_klines(symbol: str, interval: str, out_dir: Path = DATA_RAW) -> pd.DataFrame:
    path = out_dir / f"{symbol}_{interval}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} — run `mm download` first")
    return pd.read_parquet(path)
