"""DeepTrade AI — FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.api.routers import (
    auth,
    backtest,
    control,
    health,
    models,
    orders,
    pnl,
    positions,
    signals,
    trading,
)
from apps.api.streams import sse
from apps.workers.data_ingest import data_ingest
from apps.workers.paper_engine import paper_engine
from core.config import Mode, settings

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context — runs on startup/shutdown."""
    logger.info("api_starting", mode=settings.mode.value, env=settings.app_env.value)

    if settings.mode == Mode.PAPER:
        await paper_engine.start()
        await data_ingest.start(paper_engine._kite)

    yield

    if settings.mode == Mode.PAPER:
        await data_ingest.stop()
        await paper_engine.stop()

    logger.info("api_shutting_down")
    from core.db import close_engine
    await close_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI app."""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Personal AI-powered trading platform for NSE/BSE",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(signals.router, prefix="/api/v1/signals", tags=["signals"])
    app.include_router(orders.router, prefix="/api/v1/orders", tags=["orders"])
    app.include_router(positions.router, prefix="/api/v1/positions", tags=["positions"])
    app.include_router(trading.router, prefix="/api/v1/trading", tags=["trading"])
    app.include_router(pnl.router, prefix="/api/v1/pnl", tags=["pnl"])
    app.include_router(models.router, prefix="/api/v1/models", tags=["models"])
    app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["backtest"])
    app.include_router(control.router, prefix="/api/v1/control", tags=["control"])
    app.include_router(sse.router, prefix="/api/v1/stream", tags=["streams"])

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=True)
