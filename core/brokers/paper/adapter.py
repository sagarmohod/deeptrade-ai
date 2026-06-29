"""Paper broker adapter — internal fill simulator.

Always running in parallel to live. Uses the same cost model as live so
paper P&L is realistic.
"""
from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import structlog

from core.brokers.base import BrokerCostModel
from core.config import settings
from core.models import Fill, Order, OrderStatus, Position, Quote

logger = structlog.get_logger(__name__)


class PaperAdapter:
    """In-memory broker simulator."""

    name = "paper"

    def __init__(self, cost_model: BrokerCostModel) -> None:
        self.cost_model = cost_model
        self._connected = False
        self._cash: Decimal = settings.paper_simulated_capital
        self._positions: dict[str, Position] = {}
        self._fill_queue: asyncio.Queue[Fill] = asyncio.Queue()
        self._quote_provider = None  # injected at runtime to share with live

    def set_quote_provider(self, provider) -> None:  # type: ignore[no-untyped-def]
        """Plug in a quote provider (typically the same one used for live)."""
        self._quote_provider = provider

    async def connect(self) -> None:
        self._connected = True
        logger.info("paper_adapter_connected", capital=str(self._cash))

    async def disconnect(self) -> None:
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def get_available_margin(self) -> Decimal:
        # In paper mode, margin = cash + unrealized profits
        unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        return self._cash + unrealized

    async def compute_order_margin(self, order: Order) -> Decimal:
        """Estimate margin required."""
        if order.instrument_type in ("CE", "PE"):
            # Options buying — full premium
            price = order.limit_price or Decimal("100")
            return Decimal(order.qty) * price
        if order.instrument_type == "FUT":
            # Approx 15% of notional for index futures
            price = order.limit_price or Decimal("0")
            return Decimal(order.qty) * price * Decimal("0.15")
        # Equity intraday — approx 5x leverage
        price = order.limit_price or Decimal("0")
        return Decimal(order.qty) * price * Decimal("0.20")

    async def place_order(self, order: Order) -> str:
        """Simulate fill with realistic latency + slippage + costs."""
        broker_order_id = f"PAPER_{uuid4().hex[:12]}"
        order.broker_order_id = broker_order_id
        order.status = OrderStatus.SUBMITTED
        order.ts_submitted = datetime.utcnow()

        # Schedule fill
        asyncio.create_task(self._simulate_fill(order))
        return broker_order_id

    async def _simulate_fill(self, order: Order) -> None:
        """Simulate the fill happening after realistic latency."""
        # Latency 100-500ms
        latency = random.uniform(0.1, 0.5)
        await asyncio.sleep(latency)

        # Determine fill price
        if order.limit_price is not None:
            base_price = order.limit_price
        else:
            base_price = Decimal("100")  # placeholder when no quote provider

        if self._quote_provider:
            try:
                quote = await self._quote_provider.get_quote(order.symbol)
                base_price = quote.ask if order.side == "BUY" else quote.bid
            except Exception:
                pass

        # Slippage 1-15 bps
        slippage_bps = random.uniform(1, 15)
        slippage = base_price * Decimal(str(slippage_bps / 10000))
        fill_price = base_price + slippage if order.side == "BUY" else base_price - slippage

        # Compute cost via cost model
        cost = self._compute_cost(order, fill_price)

        fill = Fill(
            order_id=order.id,
            qty=order.qty,
            price=fill_price,
            fees=cost,
            slippage_bps=slippage_bps,
        )

        # Update position state
        self._update_position(order, fill_price, cost)

        # Update cash
        gross = fill_price * Decimal(order.qty)
        if order.side == "BUY":
            self._cash -= gross + cost
        else:
            self._cash += gross - cost

        # Push fill
        await self._fill_queue.put(fill)
        logger.info(
            "paper_fill",
            order_id=str(order.id),
            price=str(fill_price),
            slippage_bps=slippage_bps,
            fees=str(cost),
        )

    def _compute_cost(self, order: Order, price: Decimal) -> Decimal:
        """Apply broker cost model."""
        if order.instrument_type in ("CE", "PE"):
            return self.cost_model.equity_options(order.side, order.qty, price).total
        if order.instrument_type == "FUT":
            return self.cost_model.equity_futures(order.side, order.qty, price).total
        if order.product == "MIS":
            return self.cost_model.equity_intraday(order.side, order.qty, price).total
        return self.cost_model.equity_delivery(order.side, order.qty, price).total

    def _update_position(self, order: Order, fill_price: Decimal, cost: Decimal) -> None:
        """Track position state in memory."""
        key = f"{order.symbol}_{order.instrument_type}"
        existing = self._positions.get(key)

        if existing is None:
            self._positions[key] = Position(
                opened_at=datetime.utcnow(),
                symbol=order.symbol,
                instrument_type=order.instrument_type,
                side=order.side,
                qty=order.qty,
                avg_entry=fill_price,
                fees_total=cost,
                horizon=order.horizon,
                strategy=order.strategy,
                mode="paper",
                signal_id=order.signal_id,
            )
        else:
            # Closing or scaling
            if existing.side != order.side:
                # Reduce or close
                close_qty = min(existing.qty, order.qty)
                pnl_per_share = (
                    (fill_price - existing.avg_entry)
                    if existing.side == "BUY"
                    else (existing.avg_entry - fill_price)
                )
                realized = pnl_per_share * Decimal(close_qty) - cost
                existing.realized_pnl += realized
                existing.qty -= close_qty
                existing.fees_total += cost

                if existing.qty == 0:
                    existing.closed_at = datetime.utcnow()
                    existing.avg_exit = fill_price
            else:
                # Scale in
                total_qty = existing.qty + order.qty
                existing.avg_entry = (
                    existing.avg_entry * Decimal(existing.qty)
                    + fill_price * Decimal(order.qty)
                ) / Decimal(total_qty)
                existing.qty = total_qty
                existing.fees_total += cost

    async def cancel_order(self, broker_order_id: str) -> bool:
        # In paper, fills are scheduled immediately so cancellation is best-effort
        return True

    async def cancel_all(self) -> int:
        return 0

    async def get_order_status(self, broker_order_id: str) -> str:
        return "FILLED"  # paper fills are immediate after latency

    async def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def get_quote(self, symbol: str) -> Quote:
        if self._quote_provider:
            return await self._quote_provider.get_quote(symbol)
        # Fallback synthetic quote
        return Quote(
            symbol=symbol,
            ltp=Decimal("100"),
            bid=Decimal("99.95"),
            ask=Decimal("100.05"),
            timestamp=datetime.utcnow(),
        )

    async def stream_fills(self) -> AsyncIterator[Fill]:
        """Yield fills as they're simulated."""
        while True:
            fill = await self._fill_queue.get()
            yield fill
