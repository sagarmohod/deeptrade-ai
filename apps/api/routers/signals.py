"""Signals router — list, query signals."""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Query
from sqlalchemy import select, desc
from core.db import SignalRow, get_session

router = APIRouter()


@router.get("/")
async def list_signals(
    horizon: str | None = Query(None),
    symbol: str | None = Query(None),
    limit: int = Query(50, le=500),
) -> dict:
    """List recent signals."""
    async with get_session() as ses:
        stmt = select(SignalRow).order_by(desc(SignalRow.ts)).limit(limit)
        if horizon:
            stmt = stmt.where(SignalRow.horizon == horizon)
        if symbol:
            stmt = stmt.where(SignalRow.symbol == symbol)
        result = await ses.execute(stmt)
        rows = result.scalars().all()
    return {
        "signals": [
            {
                "id": str(r.id),
                "ts": r.ts.isoformat(),
                "symbol": r.symbol,
                "horizon": r.horizon,
                "agent": r.agent,
                "direction": r.direction,
                "confidence": float(r.confidence),
                "reasoning": r.reasoning,
                "strategy": r.strategy,
            }
            for r in rows
        ]
    }


@router.get("/top")
async def top_signals(limit: int = 20) -> dict:
    """Top stock signals for the side panel."""
    cutoff = datetime.utcnow() - timedelta(hours=4)
    async with get_session() as ses:
        stmt = (
            select(SignalRow)
            .where(SignalRow.ts >= cutoff)
            .order_by(desc(SignalRow.confidence))
            .limit(limit)
        )
        result = await ses.execute(stmt)
        rows = result.scalars().all()
    return {
        "signals": [
            {
                "symbol": r.symbol,
                "direction": r.direction,
                "confidence": float(r.confidence),
                "horizon": r.horizon,
                "ts": r.ts.isoformat(),
            }
            for r in rows
        ]
    }
