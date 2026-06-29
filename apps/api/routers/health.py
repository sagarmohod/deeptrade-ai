"""Health check endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from core.config import settings

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Liveness check."""
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "mode": settings.mode.value,
        "env": settings.app_env.value,
        "live_enabled": settings.live_trading_enabled,
    }


@router.get("/health/ready")
async def readiness() -> dict:
    """Readiness check — verify DB and Redis are reachable."""
    checks = {"api": True, "db": False, "redis": False}

    try:
        from sqlalchemy import text
        from core.db import get_session
        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:
        pass

    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.redis_url)
        await client.ping()
        await client.aclose()
        checks["redis"] = True
    except Exception:
        pass

    return {"ready": all(checks.values()), "checks": checks}
