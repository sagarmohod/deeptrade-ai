"""Order Router — the parallel paper+live track splitter (v5 §T).

Every signal goes to BOTH tracks:
  - Paper track: ALWAYS executes (simulated)
  - Live track: only if config.live.enabled AND all gates pass
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import structlog

from core.brokers.base import BrokerAdapter
from core.config import settings
from core.models import Order, OrderStatus, Signal
from core.risk import RiskEngine

logger = structlog.get_logger(__name__)


@dataclass
class OrderResult:
    """Result of an order router execution."""

    paper_order_id: str | None = None
    live_order_id: str | None = None
    paper_rejected: bool = False
    live_rejected: bool = False
    paper_reason: str = ""
    live_reason: str = ""


class OrderRouter:
    """Routes orders to paper and live tracks."""

    def __init__(
        self,
        paper_broker: BrokerAdapter,
        live_broker: BrokerAdapter | None,
        risk_engine: RiskEngine,
    ) -> None:
        self.paper_broker = paper_broker
        self.live_broker = live_broker
        self.risk_engine = risk_engine

    async def execute(self, signal: Signal, live_session: dict | None = None) -> OrderResult:
        """Execute signal on both tracks (paper always, live conditionally)."""
        result = OrderResult()

        # Build orders for both tracks
        paper_order = self._signal_to_order(signal, mode="paper")
        live_order = self._signal_to_order(signal, mode="live") if self._live_enabled() else None

        # Common pre-checks (apply to both tracks)
        common = self.risk_engine.common_check(paper_order)
        if common.is_blocked:
            result.paper_rejected = True
            result.live_rejected = True
            result.paper_reason = common.reason
            result.live_reason = common.reason
            logger.info("signal_blocked_common", signal_id=str(signal.id), reason=common.reason)
            return result

        # === PAPER TRACK ===
        try:
            paper_id = await self.paper_broker.place_order(paper_order)
            result.paper_order_id = paper_id
            logger.info(
                "paper_order_placed",
                signal_id=str(signal.id),
                paper_order_id=paper_id,
                symbol=signal.symbol,
            )
        except Exception as e:
            result.paper_rejected = True
            result.paper_reason = f"paper_engine_error: {e}"
            logger.error("paper_order_failed", error=str(e))

        # === LIVE TRACK ===
        if live_order is not None and self.live_broker is not None:
            live_check = await self.risk_engine.live_check(live_order, live_session)
            if live_check.is_blocked:
                result.live_rejected = True
                result.live_reason = live_check.reason
                logger.info(
                    "live_order_blocked",
                    signal_id=str(signal.id),
                    reason=live_check.reason,
                    detail=live_check.detail,
                )
            else:
                try:
                    live_id = await self.live_broker.place_order(live_order)
                    result.live_order_id = live_id
                    logger.info(
                        "live_order_placed",
                        signal_id=str(signal.id),
                        live_order_id=live_id,
                    )
                except Exception as e:
                    result.live_rejected = True
                    result.live_reason = f"broker_error: {e}"
                    logger.error("live_order_failed", error=str(e))
        elif live_order is not None:
            # Live order built but no live broker available
            result.live_rejected = True
            result.live_reason = "live_broker_not_connected"

        return result

    def _live_enabled(self) -> bool:
        """Live track is enabled only if all conditions met."""
        return (
            settings.live_trading_enabled
            and self.live_broker is not None
        )

    def _signal_to_order(self, signal: Signal, mode: str) -> Order:
        """Convert a signal to an order spec."""
        # Determine side from direction
        side = "BUY" if signal.direction == 1 else "SELL"

        # Get suggested price from features
        features = signal.features
        limit_price = None
        if "breakout_level" in features:
            limit_price = Decimal(str(features["breakout_level"]))
        elif "close" in features:
            limit_price = Decimal(str(features["close"]))

        # Quantity sizing — placeholder; real version uses position_sizing
        qty = self._compute_qty(signal, mode)

        instrument_type = "CE" if "CE" in signal.symbol else "PE" if "PE" in signal.symbol else "EQ"

        return Order(
            signal_id=signal.id,
            mode=mode,  # type: ignore[arg-type]
            symbol=signal.symbol,
            instrument_type=instrument_type,  # type: ignore[arg-type]
            side=side,  # type: ignore[arg-type]
            qty=qty,
            order_type="LIMIT",
            limit_price=limit_price,
            product="MIS" if signal.horizon == "scalp" else "CNC",
            algo_tag=f"algo_{settings.algo_id}_{signal.strategy or 'unk'}"[:20],
            strategy=signal.strategy,
            horizon=signal.horizon,
        )

    def _compute_qty(self, signal: Signal, mode: str) -> int:
        """Position sizing — simplified for skeleton.

        Real implementation in core.risk.sizing.
        """
        if mode == "paper":
            capital = settings.paper_simulated_capital
        else:
            capital = settings.live_deployed_capital

        # Risk 1% of capital
        risk_capital = capital * Decimal("0.01")

        # For options, full premium is risk
        if "CE" in signal.symbol or "PE" in signal.symbol:
            estimated_premium = Decimal("100")  # placeholder
            if "stop_price" in signal.features:
                estimated_premium = Decimal(str(signal.features.get("close", 100)))
            lot_size = 75  # NIFTY default
            max_lots = max(1, int(risk_capital / (estimated_premium * lot_size)))
            return max_lots * lot_size

        # Equity: stop-distance based
        stop_distance = Decimal(str(signal.features.get("stop_price", 0)))
        close = Decimal(str(signal.features.get("close", 100)))
        if stop_distance and close:
            risk_per_share = abs(close - stop_distance)
            if risk_per_share > 0:
                return max(1, int(risk_capital / risk_per_share))
        return 1
