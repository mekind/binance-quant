# money-maker

Binance spot short-term quant trading toolkit. Python 3.11+.

## Status

Stage 1 — data pipeline + offline backtester. **No live trading yet.**

Build order:
1. ✅ Project scaffolding, config, .env
2. ✅ Historical kline downloader (`mm download`)
3. ✅ Vectorized backtester + EMA-cross baseline (`mm backtest`)
4. ⬜ More strategies (volatility breakout, RSI mean-reversion)
5. ⬜ Walk-forward validation
6. ⬜ Live WebSocket feed + paper trading on Binance **Testnet**
7. ⬜ Risk manager (position sizing, daily loss cut)
8. ⬜ Real-money executor + Telegram alerts

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then edit
```

## Usage

```bash
# Download 1m BTCUSDT candles for January
mm download --symbol BTCUSDT --interval 1m --start 2025-01-01 --end 2025-02-01

# Backtest EMA(12,26)
mm backtest --symbol BTCUSDT --interval 1m --fast 12 --slow 26

# Show loaded config
mm info
```

## Layout

```
src/money_maker/
  config.py            # pydantic settings, .env loader
  data/downloader.py   # Binance REST kline fetcher → Parquet
  strategies/          # Strategy interface + implementations
  backtest/engine.py   # Vectorized next-bar-open backtester
  cli.py               # Typer entrypoint (`mm ...`)
tests/                 # Offline smoke tests
```

## Warnings

- **Never commit `.env`** — it holds API secrets.
- Always start on **Binance Testnet** (`BINANCE_TESTNET=true`) for any live-trading code.
- Backtest results without slippage, partial fills, and funding will overstate performance — treat as upper bounds.
