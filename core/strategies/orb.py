"""Opening Range Breakout (ORB) strategy.

From v7 §BB.2. Most-documented retail scalping edge.

Logic:
  1. Define opening range (high/low of first N minutes)
  2. Wait for breakout with volume confirmation + fake-breakout filters
  3. Enter in direction of breakout
  4. Stop at opposite side of range; target at 1.5× range width
"""
from __future__ import annotations

from datetime import time
from decimal import Decimal
from statistics import mean

import structlog

from core.models import Bar, Signal
from core.strategies.base import Strategy, StrategyConfig
from core.strategies.fake_breakout_filter import FakeBreakoutContext, is_real_breakout

logger = structlog.get_logger(__name__)


class OpeningRangeBreakout(Strategy):
    """ORB scalping strategy."""

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        # Read parameters with defaults (single value if not optimization mode)
        self.range_minutes: int = self._first_or_default("range_minutes", 15)
        self.breakout_buffer_pct: float = self._first_or_default("breakout_buffer_pct", 0.05)
        self.volume_threshold: float = self._first_or_default("volume_threshold", 1.5)
        self.entry_window_end_str: str = self._first_or_default("entry_window_end", "11:30")
        self.target_rr_ratio: float = self._first_or_default("target_rr_ratio", 1.5)
        self.use_fake_breakout_filter: bool = config.filters.get(
            "fake_breakout_filter", True
        )

    def _first_or_default(self, key: str, default):  # type: ignore[no-untyped-def]
        """Get param value — first element if list, value if scalar, default if missing."""
        value = self.config.parameters.get(key, default)
        if isinstance(value, list):
            return value[0] if value else default
        return value

    @property
    def required_lookback_bars(self) -> int:
        return 60  # need enough history for volume avg + filters

    async def evaluate(self, symbol: str, bars: list[Bar]) -> Signal | None:
        """Evaluate ORB entry conditions on the latest bar."""
        if len(bars) < self.required_lookback_bars:
            return None

        latest = bars[-1]
        bar_time_ist = latest.time.time()

        # Determine opening range from today's first N minutes of bars
        market_open = time(9, 15)
        range_end = time(9, 15 + self.range_minutes)

        if bar_time_ist <= range_end:
            return None  # still inside the opening range

        try:
            entry_window_end = time.fromisoformat(self.entry_window_end_str)
        except ValueError:
            entry_window_end = time(11, 30)

        if bar_time_ist > entry_window_end:
            return None  # outside entry window

        # Find today's bars
        today_date = latest.time.date()
        today_bars = [b for b in bars if b.time.date() == today_date]

        # Bars within opening range
        opening_range_bars = [
            b for b in today_bars if market_open <= b.time.time() <= range_end
        ]
        if not opening_range_bars:
            return None

        range_high = max(b.high for b in opening_range_bars)
        range_low = min(b.low for b in opening_range_bars)
        range_width = range_high - range_low

        if range_width <= 0:
            return None

        # Compute breakout thresholds
        buffer = range_high * Decimal(str(self.breakout_buffer_pct / 100))

        long_breakout_level = range_high + buffer
        short_breakout_level = range_low - buffer

        # Detect breakout
        direction = None
        if latest.close > long_breakout_level:
            direction = "above"
        elif latest.close < short_breakout_level:
            direction = "below"

        if direction is None:
            return None

        # Apply fake-breakout filter
        if self.use_fake_breakout_filter:
            ctx = FakeBreakoutContext(
                bar=latest,
                recent_bars=bars[-30:],
                breakout_level=long_breakout_level if direction == "above" else short_breakout_level,
                direction=direction,
                volume_threshold=self.volume_threshold,
                hold_n_bars=2,
                range_high=range_high,
                range_low=range_low,
            )
            filter_result = is_real_breakout(ctx)
            if not filter_result.passed:
                logger.debug(
                    "orb_filter_rejected",
                    symbol=symbol,
                    reason=filter_result.reason,
                )
                return None

        # Build signal
        signal_direction = 1 if direction == "above" else -1
        confidence = 0.7  # baseline; meta-agent can refine
        if self.use_fake_breakout_filter:
            confidence = 0.78  # higher because filter passed

        target_distance = range_width * Decimal(str(self.target_rr_ratio))
        if direction == "above":
            stop_price = range_low
            target_price = latest.close + target_distance
        else:
            stop_price = range_high
            target_price = latest.close - target_distance

        return Signal(
            ts=latest.time,
            symbol=symbol,
            horizon=self.horizon,  # type: ignore[arg-type]
            agent="technical",
            direction=signal_direction,  # type: ignore[arg-type]
            confidence=confidence,
            expected_return_pct=float(target_distance / latest.close * 100),
            expected_holding_bars=30,
            features={
                "range_high": float(range_high),
                "range_low": float(range_low),
                "range_width": float(range_width),
                "breakout_level": float(long_breakout_level if direction == "above" else short_breakout_level),
                "stop_price": float(stop_price),
                "target_price": float(target_price),
                "volume_ratio": float(latest.volume) / max(1, mean(b.volume for b in bars[-20:])),
            },
            reasoning=(
                f"ORB {'long' if direction == 'above' else 'short'} breakout. "
                f"Range: {range_low}-{range_high}. Close: {latest.close}. "
                f"{'Filter passed.' if self.use_fake_breakout_filter else 'No filter applied.'}"
            ),
            strategy=self.name,
        )
