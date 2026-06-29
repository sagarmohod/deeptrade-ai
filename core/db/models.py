"""SQLAlchemy ORM models — database tables.

Mirrors the schemas documented in v1 §4.1 + v2 §A.3 + v5 §U.2.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base."""


# ===================== TIME-SERIES TABLES =====================

class MarketBar(Base):
    """OHLCV bar at multiple timeframes. Hypertable in TimescaleDB."""

    __tablename__ = "market_bars"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(10), primary_key=True, default="NSE")
    timeframe: Mapped[str] = mapped_column(String(10), primary_key=True, default="1m")
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    vwap: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    trades: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (Index("idx_bars_symbol_time", "symbol", "time"),)


# ===================== SIGNALS =====================

class SignalRow(Base):
    """Every signal produced — even if not traded."""

    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    horizon: Mapped[str] = mapped_column(String(20))
    agent: Mapped[str] = mapped_column(String(20))
    direction: Mapped[int] = mapped_column(Integer)  # -1, 0, 1
    confidence: Mapped[float] = mapped_column(Numeric(5, 4))
    expected_return: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    expected_holding_bars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_vector: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str] = mapped_column(String(100), default="n/a")
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)


# ===================== ORDERS, FILLS, POSITIONS =====================

class OrderRow(Base):
    """An order — paper or live."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id"), nullable=True
    )
    ts_created: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ts_submitted: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ts_terminal: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    mode: Mapped[str] = mapped_column(String(20), index=True)  # paper / live / backtest
    broker: Mapped[str] = mapped_column(String(50), default="zerodha")
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    symbol: Mapped[str] = mapped_column(String(50), index=True)
    exchange: Mapped[str] = mapped_column(String(10), default="NSE")
    instrument_type: Mapped[str] = mapped_column(String(10), default="EQ")
    side: Mapped[str] = mapped_column(String(10))
    qty: Mapped[int] = mapped_column(Integer)
    order_type: Mapped[str] = mapped_column(String(20))
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    trigger_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    product: Mapped[str] = mapped_column(String(10), default="MIS")

    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    filled_qty: Mapped[int] = mapped_column(Integer, default=0)

    algo_tag: Mapped[str] = mapped_column(String(50), default="")
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    horizon: Mapped[str | None] = mapped_column(String(20), nullable=True)

    live_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("live_trading_session.id"), nullable=True
    )

    fills: Mapped[list[FillRow]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class FillRow(Base):
    """An execution event — fully or partially fills an order."""

    __tablename__ = "fills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    qty: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    slippage_bps: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)

    order: Mapped[OrderRow] = relationship(back_populates="fills")


class PositionRow(Base):
    """A held or historical position."""

    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    symbol: Mapped[str] = mapped_column(String(50), index=True)
    instrument_type: Mapped[str] = mapped_column(String(10))
    side: Mapped[str] = mapped_column(String(10))
    qty: Mapped[int] = mapped_column(Integer)

    avg_entry: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    avg_exit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    fees_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    horizon: Mapped[str | None] = mapped_column(String(20), nullable=True)
    strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), index=True)
    signal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("signals.id"), nullable=True
    )


# ===================== RISK & SESSIONS =====================

class LiveTradingSession(Base):
    """User-configured live trading session — UI sets limits, system enforces."""

    __tablename__ = "live_trading_session"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # User-set limits
    max_total_live_trades: Mapped[int] = mapped_column(Integer)
    max_live_trades_per_day: Mapped[int] = mapped_column(Integer)
    max_concurrent_positions: Mapped[int] = mapped_column(Integer)
    max_capital_at_risk_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    max_capital_per_trade: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    broker_balance_min_buffer: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("500"))
    enabled_strategies: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    # System counters
    trades_executed_total: Mapped[int] = mapped_column(Integer, default=0)
    trades_executed_today: Mapped[int] = mapped_column(Integer, default=0)
    last_day_reset: Mapped[date | None] = mapped_column(Date, nullable=True)
    capital_currently_at_risk: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))

    created_by_action: Mapped[str] = mapped_column(String(50), default="ui_enable")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskEvent(Base):
    """Risk engine events — blocks, halts, warnings."""

    __tablename__ = "risk_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    severity: Mapped[str] = mapped_column(String(20))  # INFO/WARN/BLOCK/HALT
    rule: Mapped[str] = mapped_column(String(100))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    action_taken: Mapped[str | None] = mapped_column(Text, nullable=True)


# ===================== MODEL REGISTRY =====================

class ModelRegistryRow(Base):
    """Versioned model artifacts."""

    __tablename__ = "model_registry"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[str] = mapped_column(String(100), primary_key=True)
    horizon: Mapped[str] = mapped_column(String(20))
    target: Mapped[str] = mapped_column(String(100))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    train_window_start: Mapped[date] = mapped_column(Date)
    train_window_end: Mapped[date] = mapped_column(Date)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    artifact_path: Mapped[str] = mapped_column(Text)
    feature_set_version: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[str] = mapped_column(String(30), default="CANDIDATE")
    parent_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shadow_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deprecation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


# ===================== AUDIT =====================

class AuditLog(Base):
    """Audit trail — every state-changing action."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100))
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
