"""Risk engine — pre-trade gate.

Every order passes through here before reaching the broker.
Implements all gates documented in v6 §10.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

import structlog

from core.brokers.base import BrokerAdapter
from core.config import settings
from core.models import Order

logger = structlog.get_logger(__name__)


@dataclass
class RiskDecision:
    """Result of a risk evaluation."""

    action: Literal["APPROVE", "BLOCK", "HALT"]
    reason: str = ""
    detail: dict[str, str | float | bool] | None = None

    @property
    def is_approved(self) -> bool:
        return self.action == "APPROVE"

    @property
    def is_blocked(self) -> bool:
        return self.action in ("BLOCK", "HALT")


class RiskEngine:
    """Pre-trade risk gate."""

    def __init__(self, broker: BrokerAdapter | None = None) -> None:
        self.broker = broker
        # In-memory state — would be backed by Redis / DB in full implementation
        self._kill_switch_active = False
        self._daily_pnl: Decimal = Decimal("0")
        self._weekly_pnl: Decimal = Decimal("0")
        self._open_position_count: int = 0
        # Live session counters (loaded from DB in production)
        self._live_session: dict | None = None

    # ----- Common (paper + live) -----

    def common_check(self, order: Order) -> RiskDecision:
        """Mode-agnostic checks that apply to both paper and live."""
        if self._kill_switch_active:
            return RiskDecision(action="BLOCK", reason="kill_switch_active")

        # Sanity
        if order.qty <= 0:
            return RiskDecision(action="BLOCK", reason="invalid_quantity")
        if order.limit_price is not None and order.limit_price <= 0:
            return RiskDecision(action="BLOCK", reason="invalid_price")

        return RiskDecision(action="APPROVE")

    # ----- Live-specific -----

    async def live_check(self, order: Order, session: dict | None = None) -> RiskDecision:
        """Live-only gates: UI limits, balance, loss limits."""
        if not settings.live_trading_enabled:
            return RiskDecision(
                action="BLOCK", reason="live_trading_disabled_by_env_var"
            )

        if session is None:
            return RiskDecision(action="BLOCK", reason="no_active_live_session")

        # Daily reset
        today = datetime.utcnow().date()
        if session.get("last_day_reset") != today:
            session["trades_executed_today"] = 0
            session["last_day_reset"] = today

        # 1. Strategy whitelist
        if order.strategy and session["enabled_strategies"]:
            if order.strategy not in session["enabled_strategies"]:
                return RiskDecision(action="BLOCK", reason="strategy_not_whitelisted")

        # 2. Total trade count
        if session["trades_executed_total"] >= session["max_total_live_trades"]:
            return RiskDecision(
                action="BLOCK",
                reason="max_total_trades_reached",
                detail={
                    "current": float(session["trades_executed_total"]),
                    "limit": float(session["max_total_live_trades"]),
                },
            )

        # 3. Daily count
        if session["trades_executed_today"] >= session["max_live_trades_per_day"]:
            return RiskDecision(action="BLOCK", reason="max_daily_trades_reached")

        # 4. Concurrent positions
        if self._open_position_count >= session["max_concurrent_positions"]:
            return RiskDecision(action="BLOCK", reason="max_concurrent_positions")

        # 5. Per-trade capital cap
        outlay = order.notional
        if outlay > Decimal(str(session["max_capital_per_trade"])):
            return RiskDecision(
                action="BLOCK",
                reason="per_trade_capital_exceeded",
                detail={"outlay": float(outlay)},
            )

        # 6. Total at-risk capital
        new_total = Decimal(str(session["capital_currently_at_risk"])) + outlay
        if new_total > Decimal(str(session["max_capital_at_risk_total"])):
            return RiskDecision(
                action="BLOCK", reason="total_capital_at_risk_exceeded"
            )

        # 7. Broker balance
        if self.broker is not None:
            try:
                available = await self.broker.get_available_margin()
                required = await self.broker.compute_order_margin(order)
                buffer = Decimal(str(session["broker_balance_min_buffer"]))
                if (available - required) < buffer:
                    return RiskDecision(
                        action="BLOCK",
                        reason="insufficient_broker_balance",
                        detail={
                            "available": float(available),
                            "required": float(required),
                            "buffer_needed": float(buffer),
                        },
                    )
            except Exception as e:
                logger.error("broker_balance_check_failed", error=str(e))
                return RiskDecision(action="BLOCK", reason="broker_balance_check_failed")

        # 8. Daily loss limit
        if self._daily_pnl < -settings.default_daily_loss_limit_pct / Decimal("100") * Decimal(
            str(session["max_capital_at_risk_total"])
        ):
            return RiskDecision(action="HALT", reason="daily_loss_limit_reached")

        # 9. Weekly loss limit
        if self._weekly_pnl < -settings.default_weekly_loss_limit_pct / Decimal("100") * Decimal(
            str(session["max_capital_at_risk_total"])
        ):
            return RiskDecision(action="HALT", reason="weekly_loss_limit_reached")

        return RiskDecision(action="APPROVE")

    # ----- State updates -----

    def trigger_kill_switch(self, reason: str = "manual") -> None:
        """Activate kill switch."""
        self._kill_switch_active = True
        logger.warning("kill_switch_activated", reason=reason)

    def reset_kill_switch(self) -> None:
        """Manually reset kill switch."""
        self._kill_switch_active = False
        logger.info("kill_switch_reset")

    def is_kill_switch_active(self) -> bool:
        return self._kill_switch_active

    def update_pnl(self, daily: Decimal, weekly: Decimal) -> None:
        self._daily_pnl = daily
        self._weekly_pnl = weekly

    def update_position_count(self, count: int) -> None:
        self._open_position_count = count
