"""Trading router — manual orders, auto-scalping toggles."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from core.config import Mode, settings
from core.db import LiveTradingSession, OrderRow, get_session

router = APIRouter()

_UTC = timezone.utc


# ---------- Models ----------

class ManualOrderRequest(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    qty: int = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT", "SL", "SL-M"] = "LIMIT"
    limit_price: Decimal | None = None
    trigger_price: Decimal | None = None
    product: Literal["MIS", "CNC", "NRML"] = "MIS"
    mode: Literal["paper", "live"] = "paper"
    stop_loss: Decimal | None = None
    target: Decimal | None = None
    auto_squareoff: bool = False


class AutoScalpingSettings(BaseModel):
    """Settings to enable live auto-scalping via Zerodha."""

    max_total_live_trades: int = Field(gt=0, le=200)
    max_live_trades_per_day: int = Field(gt=0, le=100)
    max_concurrent_positions: int = Field(gt=0, le=20)
    max_capital_at_risk_total: Decimal = Field(gt=0)
    max_capital_per_trade: Decimal = Field(gt=0)
    broker_balance_min_buffer: Decimal = Field(default=Decimal("500"))
    enabled_strategies: list[str] = Field(default_factory=list)
    confirmation_phrase: str = ""  # must equal "ENABLE_LIVE"


# ---------- Endpoints ----------

@router.post("/orders/manual")
async def place_manual_order(req: ManualOrderRequest) -> dict:
    if req.mode == "live" and not settings.live_trading_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Live trading not enabled. Set LIVE_TRADING_ENABLED=true.",
        )
    return {
        "ok": True,
        "message": f"Order accepted ({req.mode})",
        "echo": req.model_dump(mode="json"),
        "note": "Skeleton response — full impl wires through OrderRouter",
    }


@router.get("/auto-scalping/status")
async def get_auto_scalping_status() -> dict:
    """Return separate paper and live scalping status."""
    now_utc = datetime.now(_UTC)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    # Paper section — always enabled when mode=paper
    paper_status: dict = {"enabled": settings.mode == Mode.PAPER}
    if settings.mode == Mode.PAPER:
        async with get_session() as ses:
            trades_today = await ses.scalar(
                select(func.count()).select_from(OrderRow).where(
                    OrderRow.mode == "paper",
                    OrderRow.ts_created >= today_start,
                )
            ) or 0
            trades_total = await ses.scalar(
                select(func.count()).select_from(OrderRow).where(
                    OrderRow.mode == "paper",
                )
            ) or 0
        paper_status.update({
            "message": "Paper engine active — always on in paper mode",
            "trades_executed_today": trades_today,
            "trades_executed_total": trades_total,
            "max_capital_at_risk_total": float(settings.paper_simulated_capital),
        })

    # Live section — controlled by user toggle
    async with get_session() as ses:
        sess = await ses.scalar(
            select(LiveTradingSession).where(LiveTradingSession.is_active.is_(True))
        )

    live_status: dict
    if sess is None:
        live_status = {"enabled": False, "message": "No active live session"}
    else:
        live_status = {
            "enabled": True,
            "session_id": str(sess.id),
            "started_at": sess.started_at.isoformat(),
            "trades_executed_total": sess.trades_executed_total,
            "trades_executed_today": sess.trades_executed_today,
            "max_total_live_trades": sess.max_total_live_trades,
            "max_live_trades_per_day": sess.max_live_trades_per_day,
            "capital_currently_at_risk": float(sess.capital_currently_at_risk),
            "max_capital_at_risk_total": float(sess.max_capital_at_risk_total),
            "enabled_strategies": sess.enabled_strategies,
        }

    # Legacy top-level `enabled` for any existing callers
    return {
        "enabled": paper_status["enabled"] or live_status["enabled"],
        "paper": paper_status,
        "live": live_status,
    }


@router.post("/auto-scalping/enable")
async def enable_auto_scalping(s: AutoScalpingSettings) -> dict:
    """Enable live auto-scalping (Zerodha). Paper trading is always on."""
    if s.confirmation_phrase != "ENABLE_LIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requires confirmation_phrase='ENABLE_LIVE'",
        )
    if not settings.live_trading_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Set LIVE_TRADING_ENABLED=true in .env to allow live trading.",
        )

    now = datetime.now(_UTC)
    async with get_session() as ses:
        for old in (await ses.execute(
            select(LiveTradingSession).where(LiveTradingSession.is_active.is_(True))
        )).scalars():
            old.is_active = False
            old.ended_at = now

        new_session = LiveTradingSession(
            is_active=True,
            max_total_live_trades=s.max_total_live_trades,
            max_live_trades_per_day=s.max_live_trades_per_day,
            max_concurrent_positions=s.max_concurrent_positions,
            max_capital_at_risk_total=s.max_capital_at_risk_total,
            max_capital_per_trade=s.max_capital_per_trade,
            broker_balance_min_buffer=s.broker_balance_min_buffer,
            enabled_strategies=s.enabled_strategies,
            created_by_action="ui_enable",
        )
        ses.add(new_session)
        await ses.flush()
        session_id = new_session.id

    return {"ok": True, "session_id": str(session_id), "message": "Live auto-scalping enabled"}


@router.post("/auto-scalping/disable")
async def disable_auto_scalping() -> dict:
    """Disable live auto-scalping. Paper trading continues unaffected."""
    now = datetime.now(_UTC)
    async with get_session() as ses:
        sess = await ses.scalar(
            select(LiveTradingSession).where(LiveTradingSession.is_active.is_(True))
        )
        if sess:
            sess.is_active = False
            sess.ended_at = now

    return {"ok": True, "message": "Live auto-scalping disabled. Paper trading continues."}
