"""Kill switch: flatten the exchange-side position for a symbol.

`liquidate` is intentionally independent of any running bot — it queries the
router's free base-asset balance and market-sells all of it. That makes it a
true panic button: it works whether or not the live runner is up, and it
reconciles against the *exchange*, not the bot's in-memory state.

The CLI (`mm kill`) is a thin wrapper around this.
"""

from __future__ import annotations

from loguru import logger

from .orders import Order
from .router import OrderRouter


def base_asset(symbol: str, quote_asset: str) -> str:
    """`BTCUSDT`, quote `USDT` → `BTC`. Falls back to the symbol if no match."""
    if symbol.endswith(quote_asset):
        return symbol[: -len(quote_asset)]
    return symbol


async def liquidate(
    router: OrderRouter,
    symbol: str,
    *,
    quote_asset: str = "USDT",
    ref_price: float = 0.0,
    dust: float = 1e-8,
) -> Order | None:
    """Market-sell the entire free balance of the symbol's base asset.

    Returns the resulting SELL order, or None if the balance is below `dust`
    (nothing to liquidate).
    """
    base = base_asset(symbol, quote_asset)
    free = await router.get_free_balance(base)
    if free <= dust:
        logger.info(f"kill: no {base} balance to liquidate (free={free})")
        return None
    logger.warning(f"kill: liquidating {free} {base} on {symbol}")
    order = await router.sell(symbol, free, ref_price)
    logger.warning(
        f"kill: SOLD {order.filled_qty} {base} @ {order.avg_price:.2f} ({order.status})"
    )
    return order
