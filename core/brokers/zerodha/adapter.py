"""Zerodha Kite Connect adapter.

Wraps the official kiteconnect SDK with our standardized BrokerAdapter interface.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from core.brokers.base import BrokerAdapter
from core.config import settings
from core.models import Fill, Order, Position, Quote

logger = structlog.get_logger(__name__)


class ZerodhaAdapter:
    """Live Zerodha broker adapter via kiteconnect."""

    name = "zerodha"

    def __init__(self) -> None:
        self._kite: Any = None
        self._connected = False

    async def connect(self) -> None:
        """Initialize kite client with current access token."""
        try:
            from kiteconnect import KiteConnect
        except ImportError as e:
            raise ImportError(
                "kiteconnect not installed. Run: pip install kiteconnect"
            ) from e

        if not settings.kite_api_key:
            raise ValueError("KITE_API_KEY not configured")
        if not settings.kite_access_token:
            raise ValueError(
                "KITE_ACCESS_TOKEN not set. Run daily login script first."
            )

        self._kite = KiteConnect(api_key=settings.kite_api_key)
        self._kite.set_access_token(settings.kite_access_token)

        # Verify connection
        try:
            profile = self._kite.profile()
            logger.info("zerodha_connected", user=profile.get("user_id"))
            self._connected = True
        except Exception as e:
            logger.error("zerodha_connect_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        self._kite = None
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
    async def get_available_margin(self) -> Decimal:
        """Available margin from segment 'equity' or 'commodity'."""
        if not self._kite:
            raise RuntimeError("Not connected")
        margins = self._kite.margins(segment="equity")
        net = margins.get("net", 0)
        return Decimal(str(net))

    async def compute_order_margin(self, order: Order) -> Decimal:
        """Use kite.order_margins() for accurate per-order margin."""
        if not self._kite:
            raise RuntimeError("Not connected")

        params = [{
            "exchange": order.exchange,
            "tradingsymbol": order.symbol,
            "transaction_type": order.side,
            "variety": "regular",
            "product": order.product,
            "order_type": order.order_type,
            "quantity": order.qty,
            "price": float(order.limit_price) if order.limit_price else 0,
        }]
        result = self._kite.order_margins(params)
        if result and len(result) > 0:
            return Decimal(str(result[0].get("total", 0)))
        return Decimal("0")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=0.5, max=2))
    async def place_order(self, order: Order) -> str:
        """Place order via Kite REST. Returns broker_order_id."""
        if not self._kite:
            raise RuntimeError("Not connected")

        params = {
            "tradingsymbol": order.symbol,
            "exchange": order.exchange,
            "transaction_type": order.side,
            "quantity": order.qty,
            "order_type": order.order_type,
            "product": order.product,
            "validity": "DAY",
            "tag": order.algo_tag[:20] if order.algo_tag else f"algo_{settings.algo_id}",
        }
        if order.limit_price:
            params["price"] = float(order.limit_price)
        if order.trigger_price:
            params["trigger_price"] = float(order.trigger_price)

        broker_order_id = self._kite.place_order(variety="regular", **params)
        logger.info(
            "order_placed",
            order_id=str(order.id),
            broker_order_id=broker_order_id,
            symbol=order.symbol,
            side=order.side,
            qty=order.qty,
        )
        return str(broker_order_id)

    async def cancel_order(self, broker_order_id: str) -> bool:
        if not self._kite:
            return False
        try:
            self._kite.cancel_order(variety="regular", order_id=broker_order_id)
            return True
        except Exception as e:
            logger.error("cancel_order_failed", broker_order_id=broker_order_id, error=str(e))
            return False

    async def cancel_all(self) -> int:
        """Cancel all open orders. Returns count cancelled."""
        if not self._kite:
            return 0
        orders = self._kite.orders()
        cancelled = 0
        for o in orders:
            if o["status"] in ("OPEN", "TRIGGER PENDING"):
                if await self.cancel_order(o["order_id"]):
                    cancelled += 1
        return cancelled

    async def get_order_status(self, broker_order_id: str) -> str:
        if not self._kite:
            return "UNKNOWN"
        history = self._kite.order_history(order_id=broker_order_id)
        if history:
            return history[-1].get("status", "UNKNOWN")
        return "UNKNOWN"

    async def get_positions(self) -> list[Position]:
        """Fetch positions; convert to our Position model."""
        if not self._kite:
            return []
        kite_positions = self._kite.positions()
        result = []
        for p in kite_positions.get("net", []):
            if p["quantity"] == 0:
                continue
            result.append(self._kite_position_to_model(p))
        return result

    def _kite_position_to_model(self, p: dict[str, Any]) -> Position:
        """Convert Kite position dict to our Position."""
        from datetime import datetime

        return Position(
            opened_at=datetime.utcnow(),  # Kite doesn't give entry time directly
            symbol=p["tradingsymbol"],
            instrument_type="EQ" if p["product"] == "CNC" else "EQ",  # simplification
            side="BUY" if p["quantity"] > 0 else "SELL",
            qty=abs(p["quantity"]),
            avg_entry=Decimal(str(p["average_price"])),
            unrealized_pnl=Decimal(str(p["unrealised"])),
            mode="live",
        )

    async def get_quote(self, symbol: str) -> Quote:
        if not self._kite:
            raise RuntimeError("Not connected")
        from datetime import datetime

        full_symbol = f"NSE:{symbol}"
        data = self._kite.quote(full_symbol)
        q = data[full_symbol]
        depth = q.get("depth", {})
        bids = depth.get("buy", [])
        asks = depth.get("sell", [])

        return Quote(
            symbol=symbol,
            ltp=Decimal(str(q["last_price"])),
            bid=Decimal(str(bids[0]["price"])) if bids else Decimal(str(q["last_price"])),
            ask=Decimal(str(asks[0]["price"])) if asks else Decimal(str(q["last_price"])),
            bid_qty=bids[0]["quantity"] if bids else 0,
            ask_qty=asks[0]["quantity"] if asks else 0,
            timestamp=datetime.utcnow(),
        )

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Fills stream via postback URL — placeholder.

        In production, implement via webhook receiver. For now, poll.
        """
        # Placeholder — real implementation uses postback URL
        if False:
            yield Fill(  # type: ignore[unreachable]
                order_id=Order().id,  # type: ignore
                qty=0,
                price=Decimal("0"),
            )
