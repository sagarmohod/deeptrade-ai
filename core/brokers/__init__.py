"""Broker adapters and cost models."""
from core.brokers.base import BrokerAdapter, BrokerCostModel, CostBreakdown
from core.brokers.paper import PaperAdapter
from core.brokers.zerodha import ZerodhaAdapter, ZerodhaCostModel

# Registry of cost models
COST_MODELS: dict[str, type[BrokerCostModel]] = {
    "zerodha": ZerodhaCostModel,
}

# Registry of adapters
ADAPTERS: dict[str, type] = {
    "zerodha": ZerodhaAdapter,
    "paper": PaperAdapter,
}


def get_cost_model(name: str = "zerodha") -> BrokerCostModel:
    """Factory for cost model."""
    cls = COST_MODELS.get(name)
    if cls is None:
        raise ValueError(f"Unknown cost model: {name}")
    return cls()


__all__ = [
    "ADAPTERS",
    "COST_MODELS",
    "BrokerAdapter",
    "BrokerCostModel",
    "CostBreakdown",
    "PaperAdapter",
    "ZerodhaAdapter",
    "ZerodhaCostModel",
    "get_cost_model",
]
