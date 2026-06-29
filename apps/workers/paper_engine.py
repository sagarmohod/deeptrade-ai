"""Paper trading engine — background asyncio worker.

During NSE market hours (9:15–15:30 IST), ticks every minute:
  1. Fetches today's 1m bars from Kite REST (if configured) and upserts to DB
     (KiteTicker WebSocket ingest runs separately in data_ingest.py)
  2. Builds ML features from DB
  3. Runs all loaded models, writes SignalRow for every qualifying signal
  4. Routes signals to live Kite orders (when live session active) or paper simulation
  5. Closes positions after forward_bars minutes
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from apps.workers.event_bus import event_bus
from core.config import settings
from core.db.engine import get_session
from core.db.models import LiveTradingSession, MarketBar, OrderRow, PositionRow, SignalRow
from core.ml import SCALP_FEATURE_COLS, load_model_artifact
from core.ml.features import build_scalp_dataset_async

logger = structlog.get_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_MARKET_OPEN = time(9, 14)   # start 1 min before open so first tick has data
_MARKET_CLOSE = time(15, 31)
_TICK_SECONDS = 60

# Hardcoded instrument tokens for NSE indices (stable, never change)
_INDEX_TOKENS: dict[str, int] = {
    "NIFTY 50":   256265,
    "NIFTY BANK": 260105,
    "INDIA VIX":  264969,
}

# Model configs for live paper trading
_MODEL_CONFIGS: dict[str, dict[str, Any]] = {
    "scalp_1m": {
        "mode": "scalp",
        "symbols": ["NIFTY 50", "NIFTY BANK"],
        "exchange": "NSE",
        "timeframe": "1m",
        "feature_cols": SCALP_FEATURE_COLS,
        "forward_bars": 5,
        "bar_minutes": 1,
        "entry_threshold": 0.013,
        "fetch_hours": 4,
        "take_profit_pct": 0.003,   # exit when +0.3% above entry
        "stop_loss_pct":  0.0015,   # exit when -0.15% below entry (2:1 R:R)
    },
    "scalp_15m": {
        "mode": "scalp",
        "symbols": ["NIFTY 50", "NIFTY BANK"],
        "exchange": "NSE",
        "timeframe": "15m",
        "feature_cols": SCALP_FEATURE_COLS,
        "forward_bars": 4,
        "bar_minutes": 15,
        "entry_threshold": 0.10,
        "fetch_hours": 20,
        "take_profit_pct": 0.005,   # exit when +0.5% above entry
        "stop_loss_pct":  0.0025,   # exit when -0.25% below entry (2:1 R:R)
    },
}


@dataclass
class _OpenPosition:
    db_id: uuid.UUID
    signal_id: uuid.UUID
    symbol: str
    exchange: str
    strategy: str
    entry_price: Decimal
    qty: int
    fees_total: Decimal       # entry-leg fees; added to exit fees for net P&L
    entry_time: datetime
    close_at: datetime        # max hold time (time-based exit)
    target_price: Decimal     # take-profit level
    stop_loss_price: Decimal  # stop-loss level
    mode: str = "paper"


class PaperEngine:
    """Runs paper trading as an asyncio background task."""

    def __init__(self, models_dir: Path = Path("./models")) -> None:
        self._models_dir = models_dir
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._artifacts: dict[str, Any] = {}
        self._open_positions: list[_OpenPosition] = []
        self._kite: Any = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._running:
            return
        await self._try_connect_kite()
        self._load_models()
        self._running = True
        self._task = asyncio.create_task(self._run(), name="paper_engine")
        logger.info("paper_engine_started", n_models=len(self._artifacts))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("paper_engine_stopped")

    # ── kite connection ───────────────────────────────────────────────────────

    async def _try_connect_kite(self) -> None:
        if not settings.kite_api_key or not settings.kite_access_token:
            logger.warning(
                "kite_not_configured",
                hint="run 'make kite-login' then set KITE_ACCESS_TOKEN in .env",
            )
            return
        try:
            from core.brokers.zerodha.adapter import ZerodhaAdapter
            adapter = ZerodhaAdapter()
            await adapter.connect()
            self._kite = adapter._kite  # underlying kiteconnect client
            logger.info("paper_engine_kite_connected")
        except Exception as exc:
            logger.warning("paper_engine_kite_failed", error=str(exc))
            self._kite = None

    # ── model loading ─────────────────────────────────────────────────────────

    def _load_models(self) -> None:
        for name in _MODEL_CONFIGS:
            path = self._latest_version(name)
            if path is None:
                logger.warning("model_not_found", name=name, hint="run 'make train'")
                continue
            try:
                art = load_model_artifact(path)
                if art.booster is None:
                    logger.warning("model_booster_missing", name=name)
                    continue
                self._artifacts[name] = art
                logger.info("model_loaded", name=name, version=path.name)
            except Exception as exc:
                logger.error("model_load_error", name=name, error=str(exc))

    def _latest_version(self, name: str) -> Path | None:
        root = self._models_dir / name
        if not root.exists():
            return None
        versions = [d for d in root.iterdir() if d.is_dir() and (d / "manifest.json").exists()]
        return max(versions, key=lambda d: d.stat().st_mtime) if versions else None

    # ── main loop ─────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        while self._running:
            try:
                now_ist = datetime.now(_IST)
                if _MARKET_OPEN <= now_ist.time() <= _MARKET_CLOSE:
                    await self._tick(now_ist)
            except Exception as exc:
                logger.error("paper_engine_tick_error", error=str(exc), exc_info=True)

            # sleep to next minute boundary
            now_utc = datetime.now(timezone.utc)
            next_min = (now_utc + timedelta(seconds=_TICK_SECONDS)).replace(second=0, microsecond=0)
            await asyncio.sleep(max(1.0, (next_min - now_utc).total_seconds()))

    async def _tick(self, now_ist: datetime) -> None:
        now_utc = datetime.now(timezone.utc)
        logger.debug("paper_engine_tick", ist=now_ist.strftime("%H:%M"))

        # Publish a heartbeat so the frontend can confirm the engine is alive
        await event_bus.publish("heartbeat", {"ist": now_ist.strftime("%H:%M")})

        # 1. Ingest live bars if Kite is available
        if self._kite is not None:
            await self._ingest_live_bars(now_utc)

        # 2. Check price-based exits (take-profit / stop-loss) then time-based
        await self._check_price_exits(now_utc)
        await self._close_expired_positions(now_utc)

        # 3. Generate signals from each loaded model
        if not self._artifacts:
            return
        for name, artifact in self._artifacts.items():
            await self._process_model(name, artifact, _MODEL_CONFIGS[name], now_utc)

    # ── live data ingestion ───────────────────────────────────────────────────

    async def _ingest_live_bars(self, now_utc: datetime) -> None:
        """Fetch today's 1m and 15m bars from Kite and upsert into market_bars."""
        today = now_utc.astimezone(_IST).date()
        from_dt = datetime(today.year, today.month, today.day, 9, 0, tzinfo=_IST)
        to_dt = now_utc.astimezone(_IST)

        intervals = [("minute", "1m"), ("15minute", "15m")]
        for symbol, token in _INDEX_TOKENS.items():
            if symbol == "INDIA VIX":
                continue
            for kite_interval, tf_label in intervals:
                try:
                    raw = self._kite.historical_data(
                        instrument_token=token,
                        from_date=from_dt,
                        to_date=to_dt,
                        interval=kite_interval,
                        continuous=False,
                        oi=False,
                    )
                    if raw:
                        await self._upsert_bars(symbol, tf_label, raw)
                except Exception as exc:
                    logger.warning("kite_ingest_failed", symbol=symbol, interval=kite_interval, error=str(exc))

    async def _upsert_bars(self, symbol: str, timeframe: str, raw: list[dict]) -> None:
        rows = []
        for bar in raw:
            ts = bar["date"]
            if not ts.tzinfo:
                ts = ts.replace(tzinfo=_IST)
            rows.append({
                "time": ts,
                "symbol": symbol,
                "exchange": "NSE",
                "timeframe": timeframe,
                "open": bar["open"],
                "high": bar["high"],
                "low": bar["low"],
                "close": bar["close"],
                "volume": bar.get("volume", 0),
            })
        if not rows:
            return
        stmt = (
            insert(MarketBar)
            .values(rows)
            .on_conflict_do_nothing()
        )
        async with get_session() as session:
            await session.execute(stmt)

    # ── signal generation ─────────────────────────────────────────────────────

    async def _process_model(
        self,
        name: str,
        artifact: Any,
        meta: dict[str, Any],
        now_utc: datetime,
    ) -> None:
        # Wide lookback so we always capture the latest available historical bars
        # even when Kite is not connected and data is from a previous trading day.
        lookback_days = max(5, meta["fetch_hours"] // 24 + 3)
        start = now_utc - timedelta(days=lookback_days)
        try:
            df = await build_scalp_dataset_async(
                meta["symbols"], meta["exchange"], meta["timeframe"], start, now_utc,
            )
        except Exception as exc:
            logger.error("feature_build_failed", model=name, error=str(exc))
            return

        if df.empty:
            logger.debug("no_feature_data", model=name)
            return

        feat_cols = [c for c in meta["feature_cols"] if c in df.columns]
        df_clean = df.dropna(subset=feat_cols)
        if df_clean.empty:
            return

        # Latest bar per symbol
        symbol_col = "symbol" if "symbol" in df_clean.columns else None
        if symbol_col:
            latest_rows = df_clean.groupby("symbol").last().reset_index()
        else:
            latest_rows = df_clean.iloc[[-1]]

        kite_live = self._kite is not None  # whether we have a live feed

        for _, row in latest_rows.iterrows():
            symbol = row.get("symbol", meta["symbols"][0]) if symbol_col else meta["symbols"][0]

            # Check bar age. The feature dataset drops the last forward_bars rows
            # (they have NaN fwd_return), so the latest valid row is naturally
            # forward_bars bar-widths behind now. We add 2 extra bars as buffer.
            bar_time = row.get("time")
            if bar_time is not None:
                bt = bar_time if getattr(bar_time, "tzinfo", None) else bar_time.replace(tzinfo=timezone.utc)
                age_secs = (now_utc - bt).total_seconds()
                lag_allowance = (meta["forward_bars"] + 2) * meta["bar_minutes"] * 60
                max_stale = lag_allowance if kite_live else 86_400  # 1 day for historical-only mode
                if age_secs > max_stale:
                    logger.debug(
                        "bar_too_stale_skipped",
                        model=name, symbol=symbol,
                        age_mins=round(age_secs / 60, 1),
                        max_stale_mins=round(max_stale / 60, 1),
                        kite_live=kite_live,
                    )
                    continue
                if kite_live and age_secs > meta["bar_minutes"] * 60 * 2:
                    logger.debug(
                        "bar_lag_from_dropna",
                        model=name, symbol=symbol,
                        age_mins=round(age_secs / 60, 1),
                    )

            X = row[feat_cols].values.astype(float).reshape(1, -1)
            try:
                raw_prob = float(artifact.booster.predict(X)[0])
                prob = (
                    float(artifact.calibrator.predict(np.array([raw_prob]))[0])
                    if artifact.calibrator else raw_prob
                )
            except Exception as exc:
                logger.error("predict_failed", model=name, symbol=symbol, error=str(exc))
                continue

            logger.debug(
                "model_prediction",
                model=name, symbol=symbol,
                prob=round(prob, 4), threshold=meta["entry_threshold"],
            )

            if prob < meta["entry_threshold"]:
                continue

            logger.info(
                "paper_signal",
                model=name, symbol=symbol,
                prob=round(prob, 4), threshold=meta["entry_threshold"],
            )
            await self._open_paper_trade(name, artifact, meta, symbol, prob, now_utc)

    # ── position opening ──────────────────────────────────────────────────────

    async def _open_paper_trade(
        self,
        model_name: str,
        artifact: Any,
        meta: dict[str, Any],
        symbol: str,
        prob: float,
        now_utc: datetime,
    ) -> None:
        # Prevent duplicate open position for same symbol + strategy
        already_open = any(
            p.symbol == symbol and p.strategy == model_name
            for p in self._open_positions
        )
        if already_open:
            return

        current_price = await self._get_latest_price(symbol, meta["exchange"])
        if current_price is None or current_price <= 0:
            logger.warning("no_price_for_entry", symbol=symbol)
            return

        capital = float(settings.paper_simulated_capital)
        position_pct = 0.10
        trade_value = capital * position_pct
        qty = max(1, int(trade_value / float(current_price)))
        fees = Decimal(str(round(float(current_price) * qty * 0.0006, 2)))
        hold_minutes = meta["forward_bars"] * meta["bar_minutes"]
        close_at = now_utc + timedelta(minutes=hold_minutes)

        # Determine if we should route to live trading
        live_session = await self._get_active_live_session()
        use_live = live_session is not None and self._kite is not None
        trade_mode = "live" if use_live else "paper"

        broker_order_id: str | None = None
        if use_live:
            try:
                broker_order_id = str(self._kite.place_order(
                    variety="regular",
                    tradingsymbol=symbol,
                    exchange=meta["exchange"],
                    transaction_type="BUY",
                    quantity=qty,
                    order_type="MARKET",
                    product="MIS",
                    validity="DAY",
                    tag=f"dt_{model_name[:10]}",
                ))
                logger.info("live_order_placed", symbol=symbol, broker_order_id=broker_order_id)
            except Exception as exc:
                logger.error("live_order_failed_fallback_paper", symbol=symbol, error=str(exc))
                use_live = False
                trade_mode = "paper"
                broker_order_id = None

        signal_id = uuid.uuid4()
        order_id = uuid.uuid4()
        position_id = uuid.uuid4()

        async with get_session() as session:
            session.add(SignalRow(
                id=signal_id,
                ts=now_utc,
                symbol=symbol,
                horizon="scalp",
                agent=model_name,
                direction=1,
                confidence=round(prob, 4),
                expected_return=round(prob * 0.002, 6),
                expected_holding_bars=meta["forward_bars"],
                feature_vector={},
                model_version=getattr(artifact, "version", "unknown"),
                strategy=model_name,
            ))
            # Flush SignalRow first so the FK on OrderRow is satisfied
            await session.flush()
            session.add(OrderRow(
                id=order_id,
                signal_id=signal_id,
                ts_created=now_utc,
                ts_submitted=now_utc,
                ts_terminal=now_utc if not use_live else None,
                mode=trade_mode,
                broker="zerodha" if use_live else "paper",
                broker_order_id=broker_order_id,
                symbol=symbol,
                exchange=meta["exchange"],
                instrument_type="EQ",
                side="BUY",
                qty=qty,
                order_type="MARKET",
                product="MIS",
                status="FILLED" if not use_live else "SUBMITTED",
                filled_qty=qty if not use_live else 0,
                avg_fill_price=current_price if not use_live else None,
                strategy=model_name,
                horizon="scalp",
            ))
            session.add(PositionRow(
                id=position_id,
                opened_at=now_utc,
                symbol=symbol,
                instrument_type="EQ",
                side="BUY",
                qty=qty,
                avg_entry=current_price,
                unrealized_pnl=Decimal("0"),
                fees_total=fees,
                horizon="scalp",
                strategy=model_name,
                mode=trade_mode,
                signal_id=signal_id,
            ))

        tp = Decimal(str(round(float(current_price) * (1 + meta["take_profit_pct"]), 2)))
        sl = Decimal(str(round(float(current_price) * (1 - meta["stop_loss_pct"]),  2)))

        self._open_positions.append(_OpenPosition(
            db_id=position_id,
            signal_id=signal_id,
            symbol=symbol,
            exchange=meta["exchange"],
            strategy=model_name,
            entry_price=current_price,
            qty=qty,
            fees_total=fees,
            entry_time=now_utc,
            close_at=close_at,
            target_price=tp,
            stop_loss_price=sl,
            mode=trade_mode,
        ))

        await event_bus.publish("order", {
            "order_id": str(order_id),
            "mode": trade_mode,
            "symbol": symbol,
            "side": "BUY",
            "qty": qty,
            "status": "FILLED" if not use_live else "SUBMITTED",
            "strategy": model_name,
            "ts": now_utc.isoformat(),
        })
        await event_bus.publish("signal", {
            "signal_id": str(signal_id),
            "symbol": symbol,
            "prob": round(prob, 4),
            "model": model_name,
            "ts": now_utc.isoformat(),
        })

        logger.info(
            "trade_opened",
            mode=trade_mode, symbol=symbol, model=model_name,
            entry=float(current_price), qty=qty,
            hold_minutes=hold_minutes,
            broker_order_id=broker_order_id,
        )

    # ── position closing ──────────────────────────────────────────────────────

    async def _check_price_exits(self, now_utc: datetime) -> None:
        """Close positions that hit their take-profit or stop-loss level."""
        still_open: list[_OpenPosition] = []
        for pos in self._open_positions:
            price = await self._get_latest_price(pos.symbol, pos.exchange)
            if price is None:
                still_open.append(pos)
                continue
            if price >= pos.target_price:
                await self._close_position(pos, now_utc, reason="TARGET", exit_price=price)
            elif price <= pos.stop_loss_price:
                await self._close_position(pos, now_utc, reason="STOPLOSS", exit_price=price)
            else:
                still_open.append(pos)
        self._open_positions = still_open

    async def _close_expired_positions(self, now_utc: datetime) -> None:
        """Close positions that exceeded their max hold time."""
        expired = [p for p in self._open_positions if p.close_at <= now_utc]
        for pos in expired:
            await self._close_position(pos, now_utc, reason="TIME")
        self._open_positions = [p for p in self._open_positions if p.close_at > now_utc]

    async def _close_position(
        self,
        pos: _OpenPosition,
        now_utc: datetime,
        reason: str = "TIME",
        exit_price: Decimal | None = None,
    ) -> None:
        # Caller may pass the price that triggered the exit; fall back to DB lookup
        if exit_price is None:
            exit_price = await self._get_latest_price(pos.symbol, pos.exchange)
        if exit_price is None:
            exit_price = pos.entry_price

        use_live = pos.mode == "live" and self._kite is not None
        exit_broker_order_id: str | None = None

        if use_live:
            try:
                exit_broker_order_id = str(self._kite.place_order(
                    variety="regular",
                    tradingsymbol=pos.symbol,
                    exchange="NSE",
                    transaction_type="SELL",
                    quantity=pos.qty,
                    order_type="MARKET",
                    product="MIS",
                    validity="DAY",
                    tag=f"dt_{pos.strategy[:10]}_x",
                ))
                logger.info("live_exit_order_placed", symbol=pos.symbol, broker_order_id=exit_broker_order_id)
            except Exception as exc:
                logger.error("live_exit_order_failed", symbol=pos.symbol, error=str(exc))
                use_live = False

        gross_pnl = (exit_price - pos.entry_price) * pos.qty
        fees = Decimal(str(round(float(exit_price) * pos.qty * 0.0006, 2)))
        net_pnl = gross_pnl - fees - pos.fees_total

        exit_order_id = uuid.uuid4()
        async with get_session() as session:
            session.add(OrderRow(
                id=exit_order_id,
                signal_id=pos.signal_id,
                ts_created=now_utc,
                ts_submitted=now_utc,
                ts_terminal=now_utc if not use_live else None,
                mode=pos.mode,
                broker="zerodha" if use_live else "paper",
                broker_order_id=exit_broker_order_id,
                symbol=pos.symbol,
                exchange="NSE",
                instrument_type="EQ",
                side="SELL",
                qty=pos.qty,
                order_type="MARKET",
                product="MIS",
                status="FILLED" if not use_live else "SUBMITTED",
                filled_qty=pos.qty if not use_live else 0,
                avg_fill_price=exit_price if not use_live else None,
                strategy=pos.strategy,
                horizon="scalp",
            ))
            result = await session.execute(
                select(PositionRow).where(PositionRow.id == pos.db_id)
            )
            db_pos = result.scalar_one_or_none()
            if db_pos:
                db_pos.closed_at = now_utc
                db_pos.avg_exit = exit_price
                db_pos.realized_pnl = net_pnl
                db_pos.unrealized_pnl = Decimal("0")
                db_pos.fees_total = pos.fees_total + fees

        await event_bus.publish("order", {
            "order_id": str(exit_order_id),
            "mode": pos.mode,
            "symbol": pos.symbol,
            "side": "SELL",
            "qty": pos.qty,
            "status": "FILLED" if not use_live else "SUBMITTED",
            "strategy": pos.strategy,
            "exit_reason": reason,
            "net_pnl": float(net_pnl),
            "ts": now_utc.isoformat(),
        })

        logger.info(
            "trade_closed",
            reason=reason,
            mode=pos.mode, symbol=pos.symbol, model=pos.strategy,
            entry=float(pos.entry_price), exit=float(exit_price),
            target=float(pos.target_price), stop_loss=float(pos.stop_loss_price),
            net_pnl=float(net_pnl),
            hold_mins=round((now_utc - pos.entry_time).total_seconds() / 60, 1),
        )

    # ── live session check ────────────────────────────────────────────────────

    async def _get_active_live_session(self) -> Any | None:
        """Return the active LiveTradingSession row, or None."""
        if self._kite is None:
            return None
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(LiveTradingSession)
                    .where(LiveTradingSession.is_active.is_(True))
                    .limit(1)
                )
                return result.scalar_one_or_none()
        except Exception:
            return None

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _get_latest_price(self, symbol: str, exchange: str = "NSE") -> Decimal | None:
        try:
            async with get_session() as session:
                result = await session.execute(
                    select(MarketBar.close)
                    .where(MarketBar.symbol == symbol, MarketBar.exchange == exchange)
                    .order_by(MarketBar.time.desc())
                    .limit(1)
                )
                val = result.scalar_one_or_none()
                return Decimal(str(val)) if val is not None else None
        except Exception as exc:
            logger.error("get_latest_price_failed", symbol=symbol, error=str(exc))
            return None


# Module-level singleton — imported by main.py lifespan
paper_engine = PaperEngine()
