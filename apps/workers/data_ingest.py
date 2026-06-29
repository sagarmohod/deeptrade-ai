"""Live market data ingest — KiteTicker WebSocket → market_bars DB.

Streams real-time tick data from Zerodha KiteTicker, aggregates ticks into
completed 1m and 15m OHLCV bars, and upserts them into the market_bars table.

The ticker runs on KiteConnect's own background thread; we bridge it to the
asyncio event loop via a thread-safe queue.
"""
from __future__ import annotations

import asyncio
import queue
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.dialects.postgresql import insert

from core.config import settings
from core.db.engine import get_session
from core.db.models import MarketBar

logger = structlog.get_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_MARKET_OPEN_H, _MARKET_OPEN_M = 9, 15
_MARKET_CLOSE_H, _MARKET_CLOSE_M = 15, 30

# Instrument token → symbol name
_TOKEN_SYMBOL: dict[int, str] = {
    256265: "NIFTY 50",
    260105: "NIFTY BANK",
    264969: "INDIA VIX",
}
_SUBSCRIBE_TOKENS = [256265, 260105]  # indices used by scalp models


class _PartialBar:
    """Accumulates ticks for one OHLCV bar (one time-bucket)."""
    __slots__ = ("open", "high", "low", "close", "volume", "ts")

    def __init__(self, price: float, volume: int, ts: datetime) -> None:
        self.open = self.high = self.low = self.close = price
        self.volume = volume
        self.ts = ts

    def update(self, price: float, volume: int) -> None:
        if price > self.high:
            self.high = price
        if price < self.low:
            self.low = price
        self.close = price
        self.volume += volume


class DataIngestWorker:
    """Streams tick data from KiteTicker and writes OHLCV bars to the DB."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._tick_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
        self._bars_1m: dict[str, _PartialBar] = {}   # symbol → current 1m bar
        self._bars_15m: dict[str, _PartialBar] = {}  # symbol → current 15m bar
        self._ticker: Any = None
        self._lock = threading.Lock()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, kite: Any) -> None:
        """Start the WebSocket ticker in a background thread."""
        if self._running:
            return
        try:
            from kiteconnect import KiteTicker
        except ImportError:
            logger.warning("kiteticker_not_installed", hint="pip install kiteconnect")
            return

        if not settings.kite_api_key or not settings.kite_access_token:
            logger.warning("kite_not_configured_ingest")
            return

        self._running = True
        self._ticker = KiteTicker(settings.kite_api_key, settings.kite_access_token)
        self._ticker.on_connect = self._on_connect
        self._ticker.on_ticks = self._on_ticks
        self._ticker.on_close = self._on_close
        self._ticker.on_error = self._on_error
        self._ticker.on_reconnect = self._on_reconnect

        # KiteTicker runs its own event loop in a background thread
        threading.Thread(target=self._ticker.connect, daemon=True).start()

        # asyncio task reads from queue and writes bars to DB
        self._task = asyncio.create_task(self._drain_queue(), name="data_ingest")
        logger.info("data_ingest_started")

    async def stop(self) -> None:
        self._running = False
        if self._ticker:
            try:
                self._ticker.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("data_ingest_stopped")

    # ── KiteTicker callbacks (run in ticker's thread) ─────────────────────────

    def _on_connect(self, ws: Any, response: Any) -> None:
        ws.subscribe(_SUBSCRIBE_TOKENS)
        ws.set_mode(ws.MODE_FULL, _SUBSCRIBE_TOKENS)
        logger.info("kiteticker_connected", tokens=_SUBSCRIBE_TOKENS)

    def _on_ticks(self, ws: Any, ticks: list[dict]) -> None:
        for tick in ticks:
            try:
                self._tick_queue.put_nowait(tick)
            except queue.Full:
                pass  # drop tick; queue full

    def _on_close(self, ws: Any, code: int, reason: str) -> None:
        logger.warning("kiteticker_closed", code=code, reason=reason)

    def _on_error(self, ws: Any, code: int, reason: str) -> None:
        logger.error("kiteticker_error", code=code, reason=reason)

    def _on_reconnect(self, ws: Any, attempt: int, delay: int) -> None:
        logger.info("kiteticker_reconnecting", attempt=attempt, delay=delay)

    # ── asyncio queue drain ───────────────────────────────────────────────────

    async def _drain_queue(self) -> None:
        """Read ticks from the thread-safe queue and process them."""
        pending_bars: list[dict] = []

        while self._running:
            # Drain everything available (non-blocking)
            while not self._tick_queue.empty():
                try:
                    tick = self._tick_queue.get_nowait()
                    completed = self._process_tick(tick)
                    pending_bars.extend(completed)
                except queue.Empty:
                    break

            if pending_bars:
                await self._upsert_bars(pending_bars)
                pending_bars.clear()

            await asyncio.sleep(0.5)  # check queue every 500ms

    def _process_tick(self, tick: dict[str, Any]) -> list[dict]:
        """Aggregate tick into current bar state. Returns completed bars."""
        token = tick.get("instrument_token")
        symbol = _TOKEN_SYMBOL.get(token)
        if symbol is None:
            return []

        price = float(tick.get("last_price", 0))
        volume = int(tick.get("volume_traded", 0) or tick.get("volume", 0))
        ts_raw = tick.get("timestamp") or tick.get("exchange_timestamp")
        if ts_raw is None:
            return []

        ts: datetime = ts_raw if isinstance(ts_raw, datetime) else datetime.fromisoformat(str(ts_raw))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_IST)

        ts_utc = ts.astimezone(timezone.utc)
        completed: list[dict] = []

        for tf_minutes, bars_dict in ((1, self._bars_1m), (15, self._bars_15m)):
            bucket = _bucket_time(ts_utc, tf_minutes)
            bar = bars_dict.get(symbol)

            if bar is None:
                bars_dict[symbol] = _PartialBar(price, volume, bucket)
            elif bar.ts == bucket:
                bar.update(price, volume)
            else:
                # Bar closed — flush it
                completed.append(_bar_to_row(symbol, tf_minutes, bar))
                bars_dict[symbol] = _PartialBar(price, volume, bucket)

        return completed

    # ── DB write ──────────────────────────────────────────────────────────────

    async def _upsert_bars(self, rows: list[dict]) -> None:
        if not rows:
            return
        stmt = insert(MarketBar).values(rows).on_conflict_do_nothing()
        async with get_session() as session:
            await session.execute(stmt)
        logger.debug("bars_upserted", count=len(rows))


# ── helpers ───────────────────────────────────────────────────────────────────

def _bucket_time(ts_utc: datetime, tf_minutes: int) -> datetime:
    """Floor ts to the nearest tf_minutes boundary (UTC)."""
    total_minutes = ts_utc.hour * 60 + ts_utc.minute
    floored = (total_minutes // tf_minutes) * tf_minutes
    return ts_utc.replace(
        hour=floored // 60,
        minute=floored % 60,
        second=0,
        microsecond=0,
    )


def _timeframe_label(tf_minutes: int) -> str:
    return f"{tf_minutes}m" if tf_minutes < 60 else f"{tf_minutes // 60}h"


def _bar_to_row(symbol: str, tf_minutes: int, bar: _PartialBar) -> dict:
    return {
        "time": bar.ts,
        "symbol": symbol,
        "exchange": "NSE",
        "timeframe": _timeframe_label(tf_minutes),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


# Module-level singleton
data_ingest = DataIngestWorker()
