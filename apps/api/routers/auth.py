"""Auth router — Kite OAuth flow + session management."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from core.config import settings

router = APIRouter()


@router.get("/kite/login-url")
async def kite_login_url() -> dict:
    """Returns the Kite Connect login URL for OAuth flow."""
    if not settings.kite_api_key:
        raise HTTPException(400, "KITE_API_KEY not configured")
    return {
        "url": f"https://kite.zerodha.com/connect/login?api_key={settings.kite_api_key}&v=3",
        "instructions": "Visit URL, authenticate, you'll be redirected with request_token",
    }


@router.get("/kite/callback")
async def kite_callback(request_token: str = Query(...)) -> dict:
    """Receive request_token, exchange for access_token."""
    try:
        from kiteconnect import KiteConnect
        kite = KiteConnect(api_key=settings.kite_api_key)
        session = kite.generate_session(request_token, api_secret=settings.kite_api_secret.get_secret_value())
        access_token = session["access_token"]

        # Persist to Redis
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(settings.redis_url)
            await client.set("kite:access_token", access_token, ex=8 * 3600)
            await client.aclose()
        except Exception:
            pass

        return {
            "ok": True,
            "message": "Logged in successfully",
            "expires_in_hours": 8,
        }
    except ImportError:
        raise HTTPException(500, "kiteconnect SDK not installed")
    except Exception as e:
        raise HTTPException(500, f"Kite session generation failed: {e}")
