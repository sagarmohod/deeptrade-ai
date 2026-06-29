"""Strategy loader — loads YAML configs and instantiates strategies."""
from __future__ import annotations

from pathlib import Path

import structlog
import yaml

from core.strategies.base import Strategy, StrategyConfig
from core.strategies.connors_rsi import ConnorsRSI
from core.strategies.orb import OpeningRangeBreakout

logger = structlog.get_logger(__name__)


# Registry of strategy types
STRATEGY_TYPES: dict[str, type[Strategy]] = {
    "opening_range_breakout": OpeningRangeBreakout,
    "rsi_meanreversion": ConnorsRSI,
}


class StrategyRegistry:
    """Loads strategies from YAML and provides lookup."""

    def __init__(self, strategies_dir: Path | str) -> None:
        self.strategies_dir = Path(strategies_dir)
        self.strategies: dict[str, Strategy] = {}
        self._load_all()

    def _load_all(self) -> None:
        if not self.strategies_dir.exists():
            logger.warning("strategies_dir_missing", path=str(self.strategies_dir))
            return

        for yaml_file in self.strategies_dir.glob("*.yaml"):
            try:
                self._load_one(yaml_file)
            except Exception as e:
                logger.error("strategy_load_failed", file=str(yaml_file), error=str(e))

    def _load_one(self, yaml_file: Path) -> None:
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        if "strategy" not in data:
            raise ValueError(f"{yaml_file}: missing 'strategy' top-level key")

        cfg_dict = data["strategy"]
        config = StrategyConfig(
            name=cfg_dict["name"],
            type=cfg_dict["type"],
            enabled=cfg_dict.get("enabled", True),
            universe=cfg_dict.get("universe", []),
            instruments=cfg_dict.get("instruments", []),
            horizon=cfg_dict.get("horizon", "intraday"),
            parameters=cfg_dict.get("parameters", {}),
            filters=cfg_dict.get("filters", {}),
            entry=cfg_dict.get("entry", {}),
            exit=cfg_dict.get("exit", {}),
            position_sizing=cfg_dict.get("position_sizing", {}),
        )

        cls = STRATEGY_TYPES.get(config.type)
        if cls is None:
            raise ValueError(f"Unknown strategy type: {config.type}")

        strategy = cls(config)
        self.strategies[config.name] = strategy
        logger.info("strategy_loaded", name=config.name, type=config.type)

    def get(self, name: str) -> Strategy | None:
        return self.strategies.get(name)

    def get_active(self) -> list[Strategy]:
        return [s for s in self.strategies.values() if s.config.enabled]

    def get_by_horizon(self, horizon: str) -> list[Strategy]:
        return [s for s in self.get_active() if s.horizon == horizon]

    def reload(self) -> None:
        """Hot-reload all strategy YAMLs."""
        self.strategies.clear()
        self._load_all()
