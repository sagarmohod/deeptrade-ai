"""Connors 2-period RSI mean-reversion strategy.

From v7 §CC.3. Buy quality stocks above 200-MA when 2-RSI < threshold.
"""
from __future__ import annotations

from decimal import Decimal
from statistics import mean

import structlog

from core.models import Bar, Signal
from core.strategies.base import Strategy, StrategyConfig

logger = structlog.get_logger(__name__)


def compute_rsi(closes: list[Decimal], period: int = 2) -> Decimal:
    """Compute Wilder's RSI."""
    if len(closes) < period + 1:
        return Decimal("50")  # neutral default

    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(Decimal("0"))
        else:
            gains.append(Decimal("0"))
            losses.append(-delta)

    if len(gains) < period:
        return Decimal("50")

    avg_gain = sum(gains[-period:]) / Decimal(period)
    avg_loss = sum(losses[-period:]) / Decimal(period)

    if avg_loss == 0:
        return Decimal("100")

    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


class ConnorsRSI(Strategy):
    """Connors 2-period RSI mean reversion."""

    def __init__(self, config: StrategyConfig) -> None:
        super().__init__(config)
        self.rsi_period: int = self._first_or_default("rsi_period", 2)
        self.rsi_entry: int = self._first_or_default("rsi_entry_threshold", 5)
        self.rsi_exit: int = self._first_or_default("rsi_exit_threshold", 65)
        self.trend_filter_sma: int = self._first_or_default("trend_filter_sma", 200)
        self.max_hold_days: int = self._first_or_default("max_hold_days", 10)
        self.catastrophic_stop_pct: float = self._first_or_default(
            "catastrophic_stop_pct", 10
        )

    def _first_or_default(self, key: str, default):  # type: ignore[no-untyped-def]
        value = self.config.parameters.get(key, default)
        if isinstance(value, list):
            return value[0] if value else default
        return value

    @property
    def required_lookback_bars(self) -> int:
        return self.trend_filter_sma + 5

    async def evaluate(self, symbol: str, bars: list[Bar]) -> Signal | None:
        """Evaluate Connors entry on daily bars."""
        if len(bars) < self.required_lookback_bars:
            return None

        # Use daily bars only
        daily_bars = [b for b in bars if b.timeframe == "1d"]
        if len(daily_bars) < self.required_lookback_bars:
            return None

        closes = [b.close for b in daily_bars]
        latest = daily_bars[-1]

        # Trend filter: must be above 200 SMA
        sma = sum(closes[-self.trend_filter_sma:]) / Decimal(self.trend_filter_sma)
        if latest.close < sma:
            return None

        # Compute RSI
        rsi = compute_rsi(closes, self.rsi_period)

        # Entry condition: oversold
        if rsi >= Decimal(self.rsi_entry):
            return None

        # Avoid buying near 52-week high (per spec)
        recent_high = max(b.high for b in daily_bars[-252:])
        if latest.close > recent_high * Decimal("0.95"):
            return None

        # Build long signal
        stop_price = latest.close * Decimal(str(1 - self.catastrophic_stop_pct / 100))
        # Target: exit when RSI > exit_threshold (price-target proxy)
        avg_gain = float(mean(closes[-50:]) / latest.close - 1) * 0.05
        target_price = latest.close * Decimal(str(1 + abs(avg_gain) + 0.03))

        return Signal(
            ts=latest.time,
            symbol=symbol,
            horizon=self.horizon,  # type: ignore[arg-type]
            agent="technical",
            direction=1,
            confidence=0.65,
            expected_return_pct=3.0,
            expected_holding_bars=self.max_hold_days,
            features={
                "rsi": float(rsi),
                "sma_200": float(sma),
                "close": float(latest.close),
                "stop_price": float(stop_price),
                "target_price": float(target_price),
                "rsi_entry_threshold": self.rsi_entry,
                "rsi_exit_threshold": self.rsi_exit,
            },
            reasoning=(
                f"Connors {self.rsi_period}-RSI = {rsi:.2f} < {self.rsi_entry}. "
                f"Above {self.trend_filter_sma}-SMA. Mean-reversion long."
            ),
            strategy=self.name,
        )
