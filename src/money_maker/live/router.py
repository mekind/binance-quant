"""OrderRouter protocol and an in-memory simulator for paper trading.

The paper executor talks to whatever object implements this protocol, so we
can plug in:
  - SimulatedRouter (default) — instant fill at the price you push in,
    great for offline runs and tests.
  - BinanceTestnetRouter (Part 4) — real HTTP calls to Binance Testnet.

`buy` is quote-denominated (USDT amount) to match Binance's quoteOrderQty
field; `sell` is base-denominated (BTC qty) because that's what we hold.
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from .orders import Order, OrderStatus, apply_fill


@runtime_checkable
class OrderRouter(Protocol):
    async def buy(self, symbol: str, quote_qty: float, ref_price: float) -> Order: ...
    async def sell(self, symbol: str, base_qty: float, ref_price: float) -> Order: ...
    async def get_free_balance(self, asset: str) -> float: ...


class SimulatedRouter:
    """Fills every order immediately at `ref_price`. No slippage, no fees.

    Slippage/fee modeling is the backtest engine's job; the live pipeline is
    measured against an actual exchange. Here the sim only exists to drive
    end-to-end flows without network.

    Tracks per-asset holdings so the kill switch (`liquidate`) can query and
    flatten a simulated position the same way it would on Testnet. Base asset
    is derived by stripping `quote_asset` off the symbol.
    """

    def __init__(self, quote_asset: str = "USDT"):
        self.filled: list[Order] = []
        self.quote_asset = quote_asset
        self.holdings: dict[str, float] = {}

    def _base_of(self, symbol: str) -> str:
        if symbol.endswith(self.quote_asset):
            return symbol[: -len(self.quote_asset)]
        return symbol

    async def buy(self, symbol: str, quote_qty: float, ref_price: float) -> Order:
        if quote_qty <= 0 or ref_price <= 0:
            raise ValueError("quote_qty and ref_price must be > 0")
        qty = quote_qty / ref_price
        order = Order(
            client_id=str(uuid.uuid4()),
            symbol=symbol,
            side="BUY",
            qty=qty,
            status=OrderStatus.NEW,
        )
        filled = apply_fill(order, qty, ref_price)
        self.filled.append(filled)
        base = self._base_of(symbol)
        self.holdings[base] = self.holdings.get(base, 0.0) + qty
        return filled

    async def sell(self, symbol: str, base_qty: float, ref_price: float) -> Order:
        if base_qty <= 0 or ref_price <= 0:
            raise ValueError("base_qty and ref_price must be > 0")
        order = Order(
            client_id=str(uuid.uuid4()),
            symbol=symbol,
            side="SELL",
            qty=base_qty,
            status=OrderStatus.NEW,
        )
        filled = apply_fill(order, base_qty, ref_price)
        self.filled.append(filled)
        base = self._base_of(symbol)
        self.holdings[base] = self.holdings.get(base, 0.0) - base_qty
        return filled

    async def get_free_balance(self, asset: str) -> float:
        return self.holdings.get(asset, 0.0)
