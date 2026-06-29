"""Fake breakout / breakdown filtering — v7 §DD.

Eight independent filter layers that, combined, reduce false breakout signals
significantly. Apply across all breakout-based strategies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from statistics import mean
from typing import Literal

from core.models import Bar


@dataclass
class FilterResult:
    """Result of fake-breakout filter evaluation."""

    passed: bool
    details: dict[str, bool]
    reason: str = ""


def avg_volume(bars: list[Bar], lookback: int = 20) -> float:
    """Average volume over lookback bars."""
    if len(bars) < lookback:
        return 0
    recent = bars[-lookback:]
    return mean(b.volume for b in recent)


def compute_atr(bars: list[Bar], period: int = 14) -> Decimal:
    """Simple ATR computation."""
    if len(bars) < period + 1:
        return Decimal("0")
    trs = []
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        high = bars[i].high
        low = bars[i].low
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    if not trs[-period:]:
        return Decimal("0")
    return sum(trs[-period:]) / Decimal(period)


# ============== INDIVIDUAL FILTERS ==============

def filter_volume_confirms(bar: Bar, recent_bars: list[Bar], threshold: float = 1.5) -> bool:
    """Filter 1: Volume on breakout bar must exceed threshold × avg."""
    avg = avg_volume(recent_bars, 20)
    if avg == 0:
        return False
    return bar.volume > threshold * avg


def filter_close_beyond_level(
    bar: Bar, level: Decimal, direction: Literal["above", "below"]
) -> bool:
    """Filter 2: Bar must CLOSE beyond level, not just wick through."""
    if direction == "above":
        return bar.close > level
    return bar.close < level


def filter_holds_beyond_level(
    bars: list[Bar],
    level: Decimal,
    n_bars: int,
    direction: Literal["above", "below"],
) -> bool:
    """Filter 3: Last N bars must all close beyond the level."""
    if len(bars) < n_bars:
        return False
    recent = bars[-n_bars:]
    if direction == "above":
        return all(b.close > level for b in recent)
    return all(b.close < level for b in recent)


def filter_range_width_sane(
    range_high: Decimal,
    range_low: Decimal,
    atr: Decimal,
    min_atr: float = 0.5,
    max_atr: float = 2.0,
) -> bool:
    """Filter 4: Range should be at least 0.5×ATR but not more than 2×ATR."""
    if atr == 0:
        return False
    width = range_high - range_low
    return Decimal(str(min_atr)) * atr <= width <= Decimal(str(max_atr)) * atr


def filter_trend_aligned(
    daily_close_now: Decimal,
    sma_50: Decimal,
    sma_200: Decimal,
    direction: Literal["long", "short"],
) -> bool:
    """Filter 5: Breakout must align with higher-timeframe trend."""
    if direction == "long":
        return sma_50 > sma_200 and daily_close_now > sma_200
    return sma_50 < sma_200 and daily_close_now < sma_200


def filter_time_acceptable(ts_ist: time) -> bool:
    """Filter 6: Time-of-day filter. Reject open volatility & EOD chop."""
    if ts_ist < time(9, 30):
        return False
    if ts_ist >= time(15, 0):
        return False
    if time(14, 30) <= ts_ist < time(15, 0):
        return False  # EOD chop
    return True


def filter_volatility_regime(india_vix: float, low: float = 12, high: float = 30) -> bool:
    """Filter 7: India VIX should be in normal range."""
    return low <= india_vix <= high


def filter_market_internals(
    advance_decline_ratio: float,
    sector_rs: float,
    direction: Literal["long", "short"],
) -> bool:
    """Filter 8: Broader market should support the direction."""
    if direction == "long":
        return advance_decline_ratio > 1.0 and sector_rs > 0
    return advance_decline_ratio < 1.0 and sector_rs < 0


# ============== COMBINED FILTER ==============

@dataclass
class FakeBreakoutContext:
    """Context for fake-breakout filtering."""

    # Required
    bar: Bar
    recent_bars: list[Bar]
    breakout_level: Decimal
    direction: Literal["above", "below"]

    # Optional (when None, filter is skipped/passes by default)
    sma_50: Decimal | None = None
    sma_200: Decimal | None = None
    daily_close: Decimal | None = None
    india_vix: float | None = None
    advance_decline_ratio: float | None = None
    sector_rs: float | None = None

    # Tuning
    volume_threshold: float = 1.5
    hold_n_bars: int = 2
    range_high: Decimal | None = None
    range_low: Decimal | None = None


def is_real_breakout(ctx: FakeBreakoutContext) -> FilterResult:
    """Apply all filters. Returns combined pass/fail with details.

    Hard filters: volume, close-beyond, time, VIX (if provided)
    Soft filters: hold, range-sanity, trend, market-internals (3-of-4 required)
    """
    direction_long: Literal["long", "short"] = (
        "long" if ctx.direction == "above" else "short"
    )

    details: dict[str, bool] = {}

    # Hard filters
    details["volume_confirms"] = filter_volume_confirms(
        ctx.bar, ctx.recent_bars, ctx.volume_threshold
    )
    details["close_beyond"] = filter_close_beyond_level(
        ctx.bar, ctx.breakout_level, ctx.direction
    )
    details["time_acceptable"] = filter_time_acceptable(ctx.bar.time.time())
    if ctx.india_vix is not None:
        details["vix_regime_ok"] = filter_volatility_regime(ctx.india_vix)
    else:
        details["vix_regime_ok"] = True  # skip if data not available

    hard_filters = ["volume_confirms", "close_beyond", "time_acceptable", "vix_regime_ok"]
    if not all(details[f] for f in hard_filters):
        failed = [f for f in hard_filters if not details[f]]
        return FilterResult(
            passed=False,
            details=details,
            reason=f"hard_filter_failed: {','.join(failed)}",
        )

    # Soft filters (3-of-4 required)
    details["holds_n_bars"] = filter_holds_beyond_level(
        ctx.recent_bars, ctx.breakout_level, ctx.hold_n_bars, ctx.direction
    )
    if ctx.range_high is not None and ctx.range_low is not None:
        atr = compute_atr(ctx.recent_bars)
        details["range_width_ok"] = filter_range_width_sane(
            ctx.range_high, ctx.range_low, atr
        )
    else:
        details["range_width_ok"] = True

    if ctx.sma_50 and ctx.sma_200 and ctx.daily_close:
        details["trend_aligned"] = filter_trend_aligned(
            ctx.daily_close, ctx.sma_50, ctx.sma_200, direction_long
        )
    else:
        details["trend_aligned"] = True  # skip when data missing

    if ctx.advance_decline_ratio is not None and ctx.sector_rs is not None:
        details["market_internals_ok"] = filter_market_internals(
            ctx.advance_decline_ratio, ctx.sector_rs, direction_long
        )
    else:
        details["market_internals_ok"] = True

    soft_filters = ["holds_n_bars", "range_width_ok", "trend_aligned", "market_internals_ok"]
    soft_passed = sum(details[f] for f in soft_filters)
    if soft_passed < 3:
        failed = [f for f in soft_filters if not details[f]]
        return FilterResult(
            passed=False,
            details=details,
            reason=f"soft_filters_failed: only {soft_passed}/4 passed; failed={','.join(failed)}",
        )

    return FilterResult(passed=True, details=details, reason="all_filters_passed")
