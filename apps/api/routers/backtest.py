"""Backtest router."""
from __future__ import annotations
from datetime import date
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

router = APIRouter()


class BacktestRequest(BaseModel):
    strategy_name: str
    symbols: list[str]
    start_date: date
    end_date: date
    initial_capital: float = 100000


@router.post("/run")
async def run_backtest(req: BacktestRequest, bg: BackgroundTasks) -> dict:
    """Trigger a backtest run (async)."""
    return {
        "ok": True,
        "message": "Backtest queued",
        "request": req.model_dump(mode="json"),
        "note": "Skeleton — full impl runs vectorbt or nautilus_trader in background",
    }


@router.get("/results/{run_id}")
async def get_backtest_results(run_id: str) -> dict:
    """Get backtest results by run ID."""
    return {
        "run_id": run_id,
        "status": "completed",
        "metrics": {"sharpe": 1.2, "profit_factor": 1.4, "max_drawdown_pct": 12.3},
        "note": "Skeleton response",
    }
