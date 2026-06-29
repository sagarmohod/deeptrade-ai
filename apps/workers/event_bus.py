"""Asyncio pub/sub event bus for cross-component real-time events.

Used by the paper engine and live trading engine to push events to SSE
streams, which in turn push to connected browsers.
"""
from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    """Single-process asyncio pub/sub. Each subscriber gets its own queue."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    async def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        evt = {"type": event_type, **payload}
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(evt)
            except asyncio.QueueFull:
                dead.append(q)
        for q in dead:
            self.unsubscribe(q)


# Module-level singleton — import this everywhere
event_bus = EventBus()
