"""Orders router."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from core.db import OrderRow, get_session

router = APIRouter()

_UTC = timezone.utc


def _serialize(r: OrderRow) -> dict:
    return {
        "id": str(r.id),
        "ts_created": r.ts_created.isoformat(),
        "ts_submitted": r.ts_submitted.isoformat() if r.ts_submitted else None,
        "ts_terminal": r.ts_terminal.isoformat() if r.ts_terminal else None,
        "mode": r.mode,
        "symbol": r.symbol,
        "exchange": r.exchange,
        "side": r.side,
        "qty": r.qty,
        "order_type": r.order_type,
        "product": r.product,
        "limit_price": float(r.limit_price) if r.limit_price else None,
        "status": r.status,
        "filled_qty": r.filled_qty,
        "avg_fill_price": float(r.avg_fill_price) if r.avg_fill_price else None,
        "strategy": r.strategy,
        "horizon": r.horizon,
        "broker_order_id": r.broker_order_id,
        "signal_id": str(r.signal_id) if r.signal_id else None,
    }


@router.get("/")
async def list_orders(
    mode: Literal["paper", "live", "all"] = Query("all"),
    order_status: str | None = Query(None, alias="status"),
    limit: int = Query(200, le=1000),
) -> dict:
    async with get_session() as ses:
        stmt = select(OrderRow).order_by(desc(OrderRow.ts_created)).limit(limit)
        if mode != "all":
            stmt = stmt.where(OrderRow.mode == mode)
        if order_status:
            stmt = stmt.where(OrderRow.status == order_status)
        rows = (await ses.execute(stmt)).scalars().all()
    return {"count": len(rows), "orders": [_serialize(r) for r in rows]}


@router.get("/today")
async def todays_orders(
    mode: Literal["paper", "live", "all"] = Query("paper"),
) -> dict:
    today = datetime.now(_UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    async with get_session() as ses:
        stmt = (
            select(OrderRow)
            .where(OrderRow.ts_created >= today)
            .order_by(desc(OrderRow.ts_created))
        )
        if mode != "all":
            stmt = stmt.where(OrderRow.mode == mode)
        rows = (await ses.execute(stmt)).scalars().all()
    return {"count": len(rows), "orders": [_serialize(r) for r in rows]}


@router.get("/history")
async def order_history(
    mode: Literal["paper", "live", "all"] = Query("paper"),
    days: int = Query(30, le=365),
    limit: int = Query(500, le=2000),
) -> dict:
    from datetime import timedelta
    cutoff = datetime.now(_UTC) - timedelta(days=days)
    async with get_session() as ses:
        stmt = (
            select(OrderRow)
            .where(OrderRow.ts_created >= cutoff)
            .order_by(desc(OrderRow.ts_created))
            .limit(limit)
        )
        if mode != "all":
            stmt = stmt.where(OrderRow.mode == mode)
        rows = (await ses.execute(stmt)).scalars().all()
    return {"count": len(rows), "orders": [_serialize(r) for r in rows]}
