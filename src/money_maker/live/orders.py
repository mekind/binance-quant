"""Order representation and pure state transitions.

The state machine is intentionally tiny:

    NEW ──fill──> PARTIALLY_FILLED ──fill──> FILLED
     │                  │
     ├──── cancel ──────┴─> CANCELED
     │
     └── reject ─> REJECTED

`apply_fill` is the only mutator that grows `filled_qty` / `avg_price`. All
transitions return a *new* Order (dataclasses are frozen) so they're safe to
share across coroutines.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Literal


class OrderStatus(StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


Side = Literal["BUY", "SELL"]


@dataclass(frozen=True, slots=True)
class Order:
    client_id: str
    symbol: str
    side: Side
    qty: float             # base quantity ordered (0 if quote-driven and not yet known)
    filled_qty: float = 0.0
    avg_price: float = 0.0
    status: OrderStatus = OrderStatus.NEW

    @property
    def is_terminal(self) -> bool:
        return self.status in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED)


def apply_fill(order: Order, fill_qty: float, fill_price: float) -> Order:
    """Merge a fill into the order's running average. Idempotent on terminal orders."""
    if order.is_terminal:
        return order
    if fill_qty <= 0:
        raise ValueError("fill_qty must be > 0")
    if fill_price <= 0:
        raise ValueError("fill_price must be > 0")

    new_filled = order.filled_qty + fill_qty
    new_avg = (
        (order.filled_qty * order.avg_price + fill_qty * fill_price) / new_filled
    )
    if order.qty > 0 and new_filled >= order.qty - 1e-12:
        status = OrderStatus.FILLED
        new_filled = order.qty  # snap to declared qty to kill float fuzz
    else:
        status = OrderStatus.PARTIALLY_FILLED
    return replace(order, filled_qty=new_filled, avg_price=new_avg, status=status)


def cancel(order: Order) -> Order:
    if order.is_terminal:
        return order
    return replace(order, status=OrderStatus.CANCELED)


def reject(order: Order) -> Order:
    if order.is_terminal:
        return order
    return replace(order, status=OrderStatus.REJECTED)
