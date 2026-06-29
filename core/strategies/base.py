"""Strategy base class — all strategies inherit from this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.models import Bar, Signal


@dataclass
class StrategyConfig:
    """Configuration for a strategy."""

    name: str
    type: str
    enabled: bool = True
    universe: str | list[str] = field(default_factory=list)
    instruments: list[str] = field(default_factory=list)
    horizon: str = "intraday"
    parameters: dict[str, Any] = field(default_factory=dict)
    filters: dict[str, Any] = field(default_factory=dict)
    entry: dict[str, Any] = field(default_factory=dict)
    exit: dict[str, Any] = field(default_factory=dict)
    position_sizing: dict[str, Any] = field(default_factory=dict)


class Strategy(ABC):
    """Abstract strategy. Subclasses implement evaluate()."""

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.name = config.name
        self.horizon = config.horizon

    @abstractmethod
    async def evaluate(self, symbol: str, bars: list[Bar]) -> Signal | None:
        """Evaluate strategy for a symbol given recent bars.

        Returns Signal if entry/exit condition met; None otherwise.
        """

    @property
    def required_lookback_bars(self) -> int:
        """Minimum bars needed for evaluation."""
        return 50

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name})>"
