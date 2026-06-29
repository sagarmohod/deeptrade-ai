"""Feature engineering — loads market_bars from DB and computes model features.

Two feature sets matching v7 §BB / §CC strategies:

  scalp_features  → NIFTY 50 / BANKNIFTY index (1m, 5m, 15m)
                    No volume features (indices always have volume=0 from Zerodha)
                    Synthetic VWAP = cumulative (H+L+C)/3 per session

  swing_features  → Nifty 100 equities (1d)
                    Full volume features (real volume available for stocks)

Labels:
  scalp: 1 if forward close > entry * (1 + threshold)   [directional]
  swing: 1 if forward close > entry * (1 + threshold)
         AND price > sma200 at signal time (Connors RSI uptrend gate)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta
import structlog
from sqlalchemy import select

from core.db.engine import get_session
from core.db.models import MarketBar

logger = structlog.get_logger(__name__)

# IST offset for time-of-day features
_IST_OFFSET = pd.Timedelta("5h30min")

# Forward-return targets per timeframe (bars ahead, min return to label as 1)
SCALP_TARGETS: dict[str, tuple[int, float]] = {
    "1m":  (5,  0.002),   # 5 bars = 5 min, 0.2% threshold
    "5m":  (3,  0.002),   # 3 bars = 15 min
    "15m": (2,  0.002),   # 2 bars = 30 min
    "1h":  (2,  0.003),   # 2 bars = 2 h
    "1d":  (5,  0.005),   # 5 days, 0.5% — for swing
}


# ─────────────────────────────────────────────────────────────────────
# DB loader
# ─────────────────────────────────────────────────────────────────────

async def _load_bars_async(
    symbols: list[str],
    exchange: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Load market_bars for multiple symbols into a DataFrame."""
    async with get_session() as session:
        stmt = (
            select(MarketBar)
            .where(
                MarketBar.symbol.in_(symbols),
                MarketBar.exchange == exchange,
                MarketBar.timeframe == timeframe,
                MarketBar.time >= start,
                MarketBar.time <= end,
            )
            .order_by(MarketBar.symbol, MarketBar.time)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    if not rows:
        return pd.DataFrame()

    records = [
        {
            "time":     r.time,
            "symbol":   r.symbol,
            "open":     float(r.open),
            "high":     float(r.high),
            "low":      float(r.low),
            "close":    float(r.close),
            "volume":   int(r.volume) if r.volume else 0,
        }
        for r in rows
    ]
    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def load_bars(
    symbols: list[str],
    exchange: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Synchronous wrapper for _load_bars_async."""
    return asyncio.run(_load_bars_async(symbols, exchange, timeframe, start, end))


# ─────────────────────────────────────────────────────────────────────
# Per-symbol indicator computation
# ─────────────────────────────────────────────────────────────────────

def _add_scalp_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add scalp features to a single-symbol DataFrame (sorted by time)."""
    df = df.copy().reset_index(drop=True)
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]

    # ── Candle features ──────────────────────────────────────────────
    df["ret_1"]       = c.pct_change()
    df["ret_5"]       = c.pct_change(5)
    df["ret_10"]      = c.pct_change(10)
    df["ret_20"]      = c.pct_change(20)
    df["range_pct"]   = (h - l) / l
    df["body_pct"]    = (c - o).abs() / l
    df["upper_wick"]  = (h - c.clip(upper=o)) / l
    df["lower_wick"]  = (o.clip(upper=c) - l) / l
    df["is_bullish"]  = (c > o).astype(int)

    # ── Trend ────────────────────────────────────────────────────────
    df["sma20"]           = ta.sma(c, length=20)
    df["sma50"]           = ta.sma(c, length=50)
    df["price_vs_sma20"]  = (c / df["sma20"]) - 1
    df["price_vs_sma50"]  = (c / df["sma50"]) - 1
    df["sma20_vs_sma50"]  = (df["sma20"] / df["sma50"]) - 1

    # ── Momentum ─────────────────────────────────────────────────────
    df["rsi14"]  = ta.rsi(c, length=14)
    df["rsi2"]   = ta.rsi(c, length=2)
    df["ema9"]   = ta.ema(c, length=9)
    df["ema_vs_sma20"] = (df["ema9"] / df["sma20"]) - 1

    # ── Volatility ───────────────────────────────────────────────────
    df["atr14"]       = ta.atr(h, l, c, length=14)
    df["atr14_pct"]   = df["atr14"] / c
    df["vol_20"]      = c.rolling(20).std() / c  # normalized rolling vol

    # ── Synthetic VWAP (no real volume for indices) ──────────────────
    # Cumulative intraday (H+L+C)/3, reset each IST trading day
    df["time_ist"]   = df["time"] + _IST_OFFSET
    df["ist_date"]   = df["time_ist"].dt.date
    df["mid_price"]  = (h + l + c) / 3
    # Daily cumulative mean of mid_price (proxy for VWAP without volume)
    df["vwap_proxy"] = df.groupby("ist_date")["mid_price"].expanding().mean().values
    df["price_vs_vwap"] = (c / df["vwap_proxy"]) - 1

    # ── Time features ────────────────────────────────────────────────
    df["hour_ist"]     = df["time_ist"].dt.hour
    df["minute_ist"]   = df["time_ist"].dt.minute
    df["day_of_week"]  = df["time_ist"].dt.dayofweek  # 0=Mon
    # Session buckets: 1=opening(9:15-10:30), 2=mid(10:30-13:30), 3=closing(13:30-15:30)
    df["session"] = np.select(
        [df["hour_ist"] < 10, df["hour_ist"] < 13],
        [1, 2],
        default=3,
    ).astype(int)

    # ── Opening range (9:15–9:30 IST = 03:45–04:00 UTC) ─────────────
    # Mark bars in the opening range window
    is_or = (
        (df["time_ist"].dt.hour == 9)
        & (df["time_ist"].dt.minute.between(15, 29))
    )
    df["is_or_bar"] = is_or.astype(int)
    # Compute per-day OR high/low
    or_high = df[is_or].groupby("ist_date")["high"].max()
    or_low  = df[is_or].groupby("ist_date")["low"].min()
    df["or_high"]      = df["ist_date"].map(or_high)
    df["or_low"]       = df["ist_date"].map(or_low)
    df["or_width_pct"] = (df["or_high"] - df["or_low"]) / df["or_low"]
    df["price_vs_or_high"] = (c / df["or_high"]) - 1
    df["price_vs_or_low"]  = (c / df["or_low"]) - 1

    # ── Volatility regime ────────────────────────────────────────────
    df["atr_regime"] = df["atr14"] / df["atr14"].rolling(20).mean()

    return df


def _add_swing_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add swing features to a single-symbol DataFrame (daily bars, sorted by time)."""
    df = df.copy().reset_index(drop=True)
    o, h, l, c, v = df["open"], df["high"], df["low"], df["close"], df["volume"]

    def _ta(result) -> pd.Series:
        """Return indicator Series or NaN Series if pandas-ta returns None (too few bars)."""
        if result is None:
            return pd.Series(np.nan, index=df.index)
        return result

    # ── Returns ──────────────────────────────────────────────────────
    df["ret_1d"]  = c.pct_change(1)
    df["ret_5d"]  = c.pct_change(5)
    df["ret_10d"] = c.pct_change(10)
    df["ret_20d"] = c.pct_change(20)
    df["ret_60d"] = c.pct_change(60)

    # ── Trend ────────────────────────────────────────────────────────
    df["sma50"]          = _ta(ta.sma(c, length=50))
    df["sma200"]         = _ta(ta.sma(c, length=200))
    df["price_vs_sma50"] = (c / df["sma50"]) - 1
    df["price_vs_sma200"]= (c / df["sma200"]) - 1
    df["sma50_vs_sma200"]= (df["sma50"] / df["sma200"]) - 1
    df["above_sma200"]   = (c > df["sma200"].fillna(np.inf)).astype(int)

    # ── Momentum ─────────────────────────────────────────────────────
    df["rsi2"]   = _ta(ta.rsi(c, length=2))
    df["rsi14"]  = _ta(ta.rsi(c, length=14))
    macd_df      = ta.macd(c, fast=12, slow=26, signal=9)
    if macd_df is not None:
        df["macd_hist"] = macd_df.iloc[:, 2]  # histogram

    # ── Volume (real for equities) ───────────────────────────────────
    df["vol_ma10"]    = v.rolling(10).mean()
    df["vol_ma20"]    = v.rolling(20).mean()
    df["vol_ratio10"] = v / df["vol_ma10"]
    df["vol_ratio20"] = v / df["vol_ma20"]

    # ── Volatility ───────────────────────────────────────────────────
    df["atr14"]     = ta.atr(h, l, c, length=14)
    df["atr14_pct"] = df["atr14"] / c
    df["vol_20_pct"]= c.rolling(20).std() / c

    # ── Donchian channel (55-day, v7 §CC.2) ─────────────────────────
    df["dc55_high"]  = h.rolling(55).max()
    df["dc55_low"]   = l.rolling(55).min()
    dc_range         = df["dc55_high"] - df["dc55_low"]
    df["dc55_pos"]   = (c - df["dc55_low"]) / dc_range.replace(0, np.nan)

    # ── Candle ───────────────────────────────────────────────────────
    df["range_pct"]  = (h - l) / l
    df["body_pct"]   = (c - o).abs() / l
    df["is_bullish"] = (c > o).astype(int)

    # ── Distance from 6-month high (120 bars) ────────────────────────
    # 120-bar window vs 252 reduces warmup from ~12 months to ~6 months,
    # preserving more effective training rows from a 2-year equity dataset.
    df["hi6m"]           = h.rolling(120).max()
    df["dist_from_hi6m"] = (c / df["hi6m"]) - 1

    return df


# ─────────────────────────────────────────────────────────────────────
# Label creation
# ─────────────────────────────────────────────────────────────────────

def _add_label(df: pd.DataFrame, forward_bars: int, threshold: float) -> pd.DataFrame:
    """Add binary label: 1 if close[+forward_bars] / close - 1 > threshold."""
    df["fwd_return"] = df["close"].shift(-forward_bars) / df["close"] - 1
    df["label"]      = (df["fwd_return"] > threshold).astype(int)
    # Drop rows where forward return cannot be computed
    df = df.dropna(subset=["fwd_return"])
    return df


def _add_swing_label(df: pd.DataFrame, forward_bars: int = 5, threshold: float = 0.005) -> pd.DataFrame:
    """Swing label: 1 if forward return > threshold AND above sma200 (Connors filter)."""
    df["fwd_return"] = df["close"].shift(-forward_bars) / df["close"] - 1
    above_trend      = df.get("above_sma200", pd.Series(1, index=df.index))
    df["label"]      = ((df["fwd_return"] > threshold) & (above_trend == 1)).astype(int)
    df = df.dropna(subset=["fwd_return"])
    return df


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

SCALP_FEATURE_COLS = [
    "ret_1", "ret_5", "ret_10", "ret_20",
    "range_pct", "body_pct", "upper_wick", "lower_wick", "is_bullish",
    "price_vs_sma20", "price_vs_sma50", "sma20_vs_sma50",
    "rsi14", "rsi2", "ema_vs_sma20",
    "atr14_pct", "vol_20",
    "price_vs_vwap",
    "hour_ist", "minute_ist", "day_of_week", "session",
    "or_width_pct", "price_vs_or_high", "price_vs_or_low",
    "atr_regime",
]

SWING_FEATURE_COLS = [
    "ret_1d", "ret_5d", "ret_10d", "ret_20d", "ret_60d",
    "price_vs_sma50", "price_vs_sma200", "sma50_vs_sma200", "above_sma200",
    "rsi2", "rsi14",
    "vol_ratio10", "vol_ratio20",
    "atr14_pct", "vol_20_pct",
    "dc55_pos",
    "range_pct", "body_pct", "is_bullish",
    "dist_from_hi6m",
]


def _build_scalp_from_raw(
    raw: pd.DataFrame,
    symbols: list[str],
    timeframe: str,
    forward_bars: int | None = None,
    label_threshold: float | None = None,
) -> pd.DataFrame:
    if raw.empty:
        logger.warning("no_bars_loaded", symbols=symbols, timeframe=timeframe)
        return pd.DataFrame()
    _fb, _thr = SCALP_TARGETS.get(timeframe, (5, 0.002))
    fb  = forward_bars    if forward_bars    is not None else _fb
    thr = label_threshold if label_threshold is not None else _thr
    parts = []
    for sym, grp in raw.groupby("symbol"):
        grp = grp.sort_values("time")
        grp = _add_scalp_features(grp)
        grp = _add_label(grp, fb, thr)
        parts.append(grp)
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    keep = SCALP_FEATURE_COLS + ["label", "fwd_return", "symbol", "time"]
    df = df[[c for c in keep if c in df.columns]].dropna()
    logger.info("scalp_dataset_built", rows=len(df), symbols=len(symbols),
                timeframe=timeframe, forward_bars=fb, label_threshold=thr,
                label_rate=round(df["label"].mean(), 3))
    return df


def _build_swing_from_raw(
    raw: pd.DataFrame,
    symbols: list[str],
    forward_bars: int | None = None,
    label_threshold: float | None = None,
) -> pd.DataFrame:
    if raw.empty:
        logger.warning("no_bars_loaded", symbols=symbols, timeframe="1d")
        return pd.DataFrame()
    fb  = forward_bars    if forward_bars    is not None else 5
    thr = label_threshold if label_threshold is not None else 0.005
    parts = []
    for sym, grp in raw.groupby("symbol"):
        grp = grp.sort_values("time")
        grp = _add_swing_features(grp)
        grp = _add_swing_label(grp, forward_bars=fb, threshold=thr)
        parts.append(grp)
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    keep = SWING_FEATURE_COLS + ["label", "fwd_return", "symbol", "time"]
    df = df[[c for c in keep if c in df.columns]].dropna()
    logger.info("swing_dataset_built", rows=len(df), symbols=len(symbols),
                forward_bars=fb, label_threshold=thr,
                label_rate=round(df["label"].mean(), 3))
    return df


def build_scalp_dataset(
    symbols: list[str],
    exchange: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    forward_bars: int | None = None,
    label_threshold: float | None = None,
) -> pd.DataFrame:
    """Synchronous: load bars from DB and return scalp feature DataFrame."""
    raw = load_bars(symbols, exchange, timeframe, start, end)
    return _build_scalp_from_raw(raw, symbols, timeframe, forward_bars, label_threshold)


async def build_scalp_dataset_async(
    symbols: list[str],
    exchange: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    forward_bars: int | None = None,
    label_threshold: float | None = None,
) -> pd.DataFrame:
    """Async: call from within an existing event loop (avoids asyncpg loop reuse issues)."""
    raw = await _load_bars_async(symbols, exchange, timeframe, start, end)
    return _build_scalp_from_raw(raw, symbols, timeframe, forward_bars, label_threshold)


def build_swing_dataset(
    symbols: list[str],
    exchange: str,
    start: datetime,
    end: datetime,
    forward_bars: int | None = None,
    label_threshold: float | None = None,
) -> pd.DataFrame:
    """Synchronous: load daily bars from DB and return swing feature DataFrame."""
    raw = load_bars(symbols, exchange, "1d", start, end)
    return _build_swing_from_raw(raw, symbols, forward_bars, label_threshold)


async def build_swing_dataset_async(
    symbols: list[str],
    exchange: str,
    start: datetime,
    end: datetime,
    forward_bars: int | None = None,
    label_threshold: float | None = None,
) -> pd.DataFrame:
    """Async: call from within an existing event loop."""
    raw = await _load_bars_async(symbols, exchange, "1d", start, end)
    return _build_swing_from_raw(raw, symbols, forward_bars, label_threshold)
