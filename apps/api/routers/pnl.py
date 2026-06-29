"""P&L router — daily/weekly/monthly + tax + broker breakdown (v2 §A)."""
from __future__ import annotations
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter, Query
from sqlalchemy import and_, select
from core.db import FillRow, OrderRow, PositionRow, get_session

router = APIRouter()


def _date_range(period: str) -> tuple[date, date]:
    today = datetime.utcnow().date()
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=today.weekday()), today
    if period == "month":
        return today.replace(day=1), today
    if period == "year":
        return today.replace(month=1, day=1), today
    return today - timedelta(days=30), today


@router.get("/")
async def get_pnl(
    period: Literal["today", "week", "month", "year", "custom"] = Query("today"),
    mode: Literal["paper", "live", "compare"] = Query("paper"),
    start: date | None = Query(None),
    end: date | None = Query(None),
) -> dict:
    """Get P&L summary."""
    if period == "custom" and start and end:
        date_start, date_end = start, end
    else:
        date_start, date_end = _date_range(period)

    modes_to_query = ["paper", "live"] if mode == "compare" else [mode]

    breakdown: dict[str, dict] = {}
    for m in modes_to_query:
        async with get_session() as ses:
            stmt = (
                select(PositionRow)
                .where(PositionRow.mode == m)
                .where(PositionRow.opened_at >= datetime.combine(date_start, datetime.min.time()))
                .where(PositionRow.opened_at <= datetime.combine(date_end, datetime.max.time()))
            )
            result = await ses.execute(stmt)
            positions = result.scalars().all()

        gross_pnl = sum(p.realized_pnl for p in positions if p.closed_at)
        unrealized = sum(p.unrealized_pnl for p in positions if not p.closed_at)
        fees = sum(p.fees_total for p in positions)
        n_wins = sum(1 for p in positions if p.closed_at and p.realized_pnl > 0)
        n_losses = sum(1 for p in positions if p.closed_at and p.realized_pnl <= 0)

        breakdown[m] = {
            "gross_pnl": float(gross_pnl),
            "unrealized_pnl": float(unrealized),
            "fees_total": float(fees),
            "net_pnl": float(gross_pnl + unrealized - fees),
            "n_trades": len([p for p in positions if p.closed_at]),
            "n_wins": n_wins,
            "n_losses": n_losses,
            "hit_rate": (n_wins / max(1, n_wins + n_losses)) if (n_wins + n_losses) else 0,
        }

    return {
        "period": period,
        "date_start": date_start.isoformat(),
        "date_end": date_end.isoformat(),
        "breakdown": breakdown,
    }


@router.get("/daily-equity-curve")
async def daily_equity_curve(
    days: int = Query(30, le=365),
    mode: Literal["paper", "live", "both"] = Query("both"),
) -> dict:
    """Equity curve for charting."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    out: dict[str, list] = {}
    modes = ["paper", "live"] if mode == "both" else [mode]

    for m in modes:
        async with get_session() as ses:
            stmt = (
                select(PositionRow)
                .where(PositionRow.mode == m)
                .where(PositionRow.opened_at >= cutoff)
                .where(PositionRow.closed_at.is_not(None))
                .order_by(PositionRow.closed_at)
            )
            result = await ses.execute(stmt)
            positions = result.scalars().all()

        cumulative = Decimal("0")
        points = []
        for p in positions:
            cumulative += (p.realized_pnl - p.fees_total)
            points.append({
                "ts": p.closed_at.isoformat() if p.closed_at else None,
                "pnl": float(cumulative),
            })
        out[m] = points

    return {"curves": out}
