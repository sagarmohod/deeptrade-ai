"""Broker adapter Protocol — common interface across Zerodha, Paper, etc."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable

from core.models import Fill, Order, Position, Quote


@dataclass
class CostBreakdown:
    """Itemized cost for a single fill."""

    brokerage: Decimal = Decimal("0")
    stt: Decimal = Decimal("0")
    ctt: Decimal = Decimal("0")
    exchange_txn: Decimal = Decimal("0")
    sebi_fee: Decimal = Decimal("0")
    gst: Decimal = Decimal("0")
    stamp_duty: Decimal = Decimal("0")
    ipft: Decimal = Decimal("0")
    other: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return (
            self.brokerage
            + self.stt
            + self.ctt
            + self.exchange_txn
            + self.sebi_fee
            + self.gst
            + self.stamp_duty
            + self.ipft
            + self.other
        )


class BrokerCostModel(Protocol):
    """Pluggable cost model — one per broker."""

    name: str
    display_name: str

    def equity_intraday(self, side: str, qty: int, price: Decimal) -> CostBreakdown: ...
    def equity_delivery(self, side: str, qty: int, price: Decimal) -> CostBreakdown: ...
    def equity_futures(self, side: str, qty: int, price: Decimal) -> CostBreakdown: ...
    def equity_options(self, side: str, qty: int, premium: Decimal) -> CostBreakdown: ...


@runtime_checkable
class BrokerAdapter(Protocol):
    """Common broker interface — Zerodha, Alpaca, Paper, etc."""

    name: str

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def is_connected(self) -> bool: ...

    # Account / margin
    async def get_available_margin(self) -> Decimal: ...
    async def compute_order_margin(self, order: Order) -> Decimal: ...

    # Orders
    async def place_order(self, order: Order) -> str: ...
    async def cancel_order(self, broker_order_id: str) -> bool: ...
    async def cancel_all(self) -> int: ...
    async def get_order_status(self, broker_order_id: str) -> str: ...

    # Positions
    async def get_positions(self) -> list[Position]: ...

    # Market data
    async def get_quote(self, symbol: str) -> Quote: ...

    # Stream of fills (live broker only — paper sim emits internally)
    async def stream_fills(self) -> AsyncIterator[Fill]: ...
