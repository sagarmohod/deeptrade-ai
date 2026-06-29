"""Initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-04 12:00:00

Creates all DeepTrade AI tables based on core.db.models.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # market_bars
    op.create_table(
        "market_bars",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("exchange", sa.String(10), nullable=False, server_default="NSE"),
        sa.Column("timeframe", sa.String(10), nullable=False, server_default="1m"),
        sa.Column("open", sa.Numeric(18, 6), nullable=False),
        sa.Column("high", sa.Numeric(18, 6), nullable=False),
        sa.Column("low", sa.Numeric(18, 6), nullable=False),
        sa.Column("close", sa.Numeric(18, 6), nullable=False),
        sa.Column("volume", sa.BigInteger, server_default="0"),
        sa.Column("vwap", sa.Numeric(18, 6), nullable=True),
        sa.Column("trades", sa.Integer, nullable=True),
        sa.PrimaryKeyConstraint("time", "symbol", "exchange", "timeframe"),
    )
    op.create_index("idx_bars_symbol_time", "market_bars", ["symbol", "time"])

    # signals
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("symbol", sa.String(50), nullable=False, index=True),
        sa.Column("horizon", sa.String(20), nullable=False),
        sa.Column("agent", sa.String(20), nullable=False),
        sa.Column("direction", sa.Integer, nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("expected_return", sa.Numeric(10, 6), nullable=True),
        sa.Column("expected_holding_bars", sa.Integer, nullable=True),
        sa.Column("feature_vector", postgresql.JSONB, server_default="{}"),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("model_version", sa.String(100), nullable=False, server_default="n/a"),
        sa.Column("strategy", sa.String(100), nullable=True),
    )

    # live_trading_session
    op.create_table(
        "live_trading_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("max_total_live_trades", sa.Integer, nullable=False),
        sa.Column("max_live_trades_per_day", sa.Integer, nullable=False),
        sa.Column("max_concurrent_positions", sa.Integer, nullable=False),
        sa.Column("max_capital_at_risk_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("max_capital_per_trade", sa.Numeric(18, 2), nullable=False),
        sa.Column("broker_balance_min_buffer", sa.Numeric(18, 2), server_default="500"),
        sa.Column("enabled_strategies", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("trades_executed_total", sa.Integer, server_default="0"),
        sa.Column("trades_executed_today", sa.Integer, server_default="0"),
        sa.Column("last_day_reset", sa.Date, nullable=True),
        sa.Column("capital_currently_at_risk", sa.Numeric(18, 2), server_default="0"),
        sa.Column("created_by_action", sa.String(50), server_default="ui_enable"),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # orders
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("ts_created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ts_submitted", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ts_terminal", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False, index=True),
        sa.Column("broker", sa.String(50), server_default="zerodha"),
        sa.Column("broker_order_id", sa.String(100), nullable=True, index=True),
        sa.Column("symbol", sa.String(50), nullable=False, index=True),
        sa.Column("exchange", sa.String(10), server_default="NSE"),
        sa.Column("instrument_type", sa.String(10), server_default="EQ"),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("limit_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("trigger_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("product", sa.String(10), server_default="MIS"),
        sa.Column("status", sa.String(20), server_default="PENDING"),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("avg_fill_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("filled_qty", sa.Integer, server_default="0"),
        sa.Column("algo_tag", sa.String(50), server_default=""),
        sa.Column("strategy", sa.String(100), nullable=True),
        sa.Column("horizon", sa.String(20), nullable=True),
        sa.Column("live_session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("live_trading_session.id"), nullable=True),
    )

    # fills
    op.create_table(
        "fills",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("fees", sa.Numeric(18, 4), server_default="0"),
        sa.Column("slippage_bps", sa.Numeric(10, 4), nullable=True),
    )

    # positions
    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("symbol", sa.String(50), nullable=False, index=True),
        sa.Column("instrument_type", sa.String(10), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("qty", sa.Integer, nullable=False),
        sa.Column("avg_entry", sa.Numeric(18, 6), nullable=False),
        sa.Column("avg_exit", sa.Numeric(18, 6), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(18, 4), server_default="0"),
        sa.Column("unrealized_pnl", sa.Numeric(18, 4), server_default="0"),
        sa.Column("fees_total", sa.Numeric(18, 4), server_default="0"),
        sa.Column("horizon", sa.String(20), nullable=True),
        sa.Column("strategy", sa.String(100), nullable=True),
        sa.Column("mode", sa.String(20), nullable=False, index=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("signals.id"), nullable=True),
    )

    # risk_events
    op.create_table(
        "risk_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("rule", sa.String(100), nullable=False),
        sa.Column("detail", postgresql.JSONB, server_default="{}"),
        sa.Column("action_taken", sa.Text, nullable=True),
    )

    # model_registry
    op.create_table(
        "model_registry",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("version", sa.String(100), primary_key=True),
        sa.Column("horizon", sa.String(20), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_window_start", sa.Date, nullable=False),
        sa.Column("train_window_end", sa.Date, nullable=False),
        sa.Column("metrics", postgresql.JSONB, server_default="{}"),
        sa.Column("artifact_path", sa.Text, nullable=False),
        sa.Column("feature_set_version", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("false")),
        sa.Column("state", sa.String(30), server_default="CANDIDATE"),
        sa.Column("parent_version", sa.String(100), nullable=True),
        sa.Column("shadow_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecation_reason", sa.Text, nullable=True),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target", sa.String(200), nullable=True),
        sa.Column("detail", postgresql.JSONB, server_default="{}"),
    )

    # Convert market_bars to TimescaleDB hypertable
    op.execute("SELECT create_hypertable('market_bars', 'time', if_not_exists => TRUE);")


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("model_registry")
    op.drop_table("risk_events")
    op.drop_table("positions")
    op.drop_table("fills")
    op.drop_table("orders")
    op.drop_table("live_trading_session")
    op.drop_table("signals")
    op.drop_index("idx_bars_symbol_time")
    op.drop_table("market_bars")
