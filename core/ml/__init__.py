"""ML pipeline."""
from core.ml.features import (
    SCALP_FEATURE_COLS,
    SWING_FEATURE_COLS,
    build_scalp_dataset,
    build_swing_dataset,
)
from core.ml.metrics import (
    QualityMetrics,
    compute_composite_score,
    compute_metrics_from_trades,
    deflated_sharpe_ratio,
)
from core.ml.registry import ModelRegistry
from core.ml.training import (
    ModelArtifact,
    WalkForwardWindow,
    build_walk_forward_schedule,
    load_model_artifact,
    make_version_string,
    progressive_training_stages,
    save_model_artifact,
)

__all__ = [
    "ModelArtifact",
    "ModelRegistry",
    "QualityMetrics",
    "SCALP_FEATURE_COLS",
    "SWING_FEATURE_COLS",
    "WalkForwardWindow",
    "build_scalp_dataset",
    "build_swing_dataset",
    "build_walk_forward_schedule",
    "compute_composite_score",
    "compute_metrics_from_trades",
    "deflated_sharpe_ratio",
    "load_model_artifact",
    "make_version_string",
    "progressive_training_stages",
    "save_model_artifact",
]
