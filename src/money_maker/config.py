"""Centralized settings loaded from .env."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True

    base_quote: str = "USDT"
    default_symbol: str = "BTCUSDT"
    default_interval: str = "1m"

    max_position_usdt: float = Field(default=100.0, ge=0)
    max_daily_loss_usdt: float = Field(default=20.0, ge=0)


settings = Settings()
