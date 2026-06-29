"""Server-Sent Events streams — real-time order, signal, and P&L updates."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from apps.workers.event_bus import event_bus

router = APIRouter()

_HEARTBEAT_INTERVAL = 20  # seconds between keepalive pings


async def _event_generator(request: Request, event_filter: str | None = None):
    """Subscribe to event_bus and stream matching events to the client.

    Uses asyncio.wait_for so events are delivered immediately when published,
    rather than waiting for a fixed polling interval.
    """
    q = event_bus.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                # Block until an event arrives, or send a heartbeat on timeout
                evt = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_INTERVAL)
                if event_filter is None or evt.get("type") == event_filter:
                    yield f"data: {json.dumps(evt)}\n\n"
            except asyncio.TimeoutError:
                now = datetime.now(timezone.utc).isoformat()
                yield f"data: {json.dumps({'type': 'heartbeat', 'ts': now})}\n\n"
    finally:
        event_bus.unsubscribe(q)


@router.get("/orders")
async def stream_orders(request: Request) -> StreamingResponse:
    """SSE stream of order events (filled, submitted, cancelled)."""
    return StreamingResponse(
        _event_generator(request, event_filter="order"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/signals")
async def stream_signals(request: Request) -> StreamingResponse:
    """SSE stream of new signal events."""
    return StreamingResponse(
        _event_generator(request, event_filter="signal"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/all")
async def stream_all(request: Request) -> StreamingResponse:
    """SSE stream of all events (orders + signals + heartbeats)."""
    return StreamingResponse(
        _event_generator(request, event_filter=None),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/status")
async def stream_status(request: Request) -> StreamingResponse:
    """SSE stream of engine heartbeats — lets the frontend show engine liveness."""
    return StreamingResponse(
        _event_generator(request, event_filter="heartbeat"),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
