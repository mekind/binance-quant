"""Binance spot Testnet REST router for market orders.

Implements the same `OrderRouter` protocol as `SimulatedRouter` but talks to
`https://testnet.binance.vision`. Uses HMAC-SHA256 query signing per the
Binance spec.

This module is intentionally minimal — only the surface PaperExecutor
needs: signed POST /api/v3/order with MARKET type. No order cancellation,
no balance fetch, no userDataStream. Those land if/when needed.

Real testnet API keys are required. Without them every call will 401.
"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from urllib.parse import urlencode

import httpx

from .orders import Order, OrderStatus

TESTNET_BASE = "https://testnet.binance.vision"
PROD_BASE = "https://api.binance.com"


def _sign(secret: str, query: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def _parse_fills(payload: dict) -> tuple[float, float]:
    """Return (total_filled_qty, weighted_avg_price) from a Binance MARKET order
    response. Caller must have requested newOrderRespType=FULL so `fills` is
    guaranteed to be present and populated."""
    fills = payload["fills"]
    total_qty = 0.0
    total_quote = 0.0
    for f in fills:
        q = float(f["qty"])
        p = float(f["price"])
        total_qty += q
        total_quote += q * p
    avg = total_quote / total_qty if total_qty > 0 else 0.0
    return total_qty, avg


class BinanceTestnetRouter:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        testnet: bool = True,
        client: httpx.AsyncClient | None = None,
        recv_window: int = 5000,
    ):
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret are required")
        self.api_key = api_key
        self.api_secret = api_secret
        self.base = TESTNET_BASE if testnet else PROD_BASE
        self.client = client or httpx.AsyncClient(timeout=10.0)
        self.recv_window = recv_window

    async def _signed_post(self, path: str, params: dict) -> dict:
        params = {**params, "timestamp": int(time.time() * 1000), "recvWindow": self.recv_window}
        query = urlencode(params)
        params["signature"] = _sign(self.api_secret, query)
        resp = await self.client.post(
            f"{self.base}{path}",
            params=params,
            headers={"X-MBX-APIKEY": self.api_key},
        )
        resp.raise_for_status()
        return resp.json()

    async def _market_order(
        self,
        symbol: str,
        side: str,
        *,
        quote_qty: float | None = None,
        base_qty: float | None = None,
    ) -> Order:
        params: dict = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "newOrderRespType": "FULL",
        }
        if quote_qty is not None:
            params["quoteOrderQty"] = f"{quote_qty:.8f}"
        elif base_qty is not None:
            params["quantity"] = f"{base_qty:.8f}"
        else:
            raise ValueError("provide quote_qty or base_qty")

        payload = await self._signed_post("/api/v3/order", params)
        filled_qty, avg_price = _parse_fills(payload)
        return Order(
            client_id=str(payload.get("clientOrderId") or uuid.uuid4()),
            symbol=symbol,
            side=side,  # type: ignore[arg-type]
            qty=filled_qty,
            filled_qty=filled_qty,
            avg_price=avg_price,
            status=OrderStatus.FILLED,
        )

    async def buy(self, symbol: str, quote_qty: float, ref_price: float) -> Order:
        del ref_price  # exchange decides actual fill price
        return await self._market_order(symbol, "BUY", quote_qty=quote_qty)

    async def sell(self, symbol: str, base_qty: float, ref_price: float) -> Order:
        del ref_price
        return await self._market_order(symbol, "SELL", base_qty=base_qty)

    async def aclose(self) -> None:
        await self.client.aclose()
