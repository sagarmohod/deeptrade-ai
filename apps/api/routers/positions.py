"""Positions router."""
from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Query
from sqlalchemy import select
from core.db import PositionRow, get_session

router = APIRouter()


@router.get("/")
async def list_positions(
    mode: Literal["paper", "live", "all"] = Query("all"),
    open_only: bool = Query(True),
) -> dict:
    """List positions."""
    async with get_session() as ses:
        stmt = select(PositionRow)
        if mode != "all":
            stmt = stmt.where(PositionRow.mode == mode)
        if open_only:
            stmt = stmt.where(PositionRow.closed_at.is_(None))
        result = await ses.execute(stmt)
        rows = result.scalars().all()
    return {
        "positions": [
            {
                "id": str(r.id),
                "symbol": r.symbol,
                "instrument_type": r.instrument_type,
                "side": r.side,
                "qty": r.qty,
                "avg_entry": float(r.avg_entry),
                "avg_exit": float(r.avg_exit) if r.avg_exit else None,
                "realized_pnl": float(r.realized_pnl),
                "unrealized_pnl": float(r.unrealized_pnl),
                "fees_total": float(r.fees_total),
                "mode": r.mode,
                "horizon": r.horizon,
                "strategy": r.strategy,
                "opened_at": r.opened_at.isoformat(),
                "closed_at": r.closed_at.isoformat() if r.closed_at else None,
                "is_open": r.closed_at is None,
            }
            for r in rows
        ]
    }
