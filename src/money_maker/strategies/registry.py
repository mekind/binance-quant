"""Strategy registry — name → constructor mapping for the CLI."""

from __future__ import annotations

from collections.abc import Callable

from .base import Strategy
from .bbands_atr import BBandsAtr
from .ema_cross import EmaCross
from .rsi_mr import RsiMeanReversion
from .vol_breakout import VolBreakout

REGISTRY: dict[str, Callable[..., Strategy]] = {
    EmaCross.name: EmaCross,
    VolBreakout.name: VolBreakout,
    RsiMeanReversion.name: RsiMeanReversion,
    BBandsAtr.name: BBandsAtr,
}


def build(name: str, **kwargs) -> Strategy:
    if name not in REGISTRY:
        raise KeyError(f"Unknown strategy '{name}'. Available: {list(REGISTRY)}")
    return REGISTRY[name](**kwargs)


def list_names() -> list[str]:
    return list(REGISTRY)
