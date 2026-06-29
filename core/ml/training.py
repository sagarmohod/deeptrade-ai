"""Model training — progressive training protocol from v4 §N + v7 §EE.

Run on Mac, deploys to VPS. Walk-forward, anti-leakage, robust parameter selection.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ModelArtifact:
    """Container for a trained model and its metadata."""

    name: str
    version: str
    horizon: str
    target: str
    trained_at: datetime
    train_window_start: date
    train_window_end: date
    artifact_path: Path
    feature_set_version: str
    metrics: dict[str, Any] = field(default_factory=dict)
    parent_version: str | None = None
    state: str = "CANDIDATE"
    booster: Any = None  # the actual LightGBM booster
    calibrator: Any = None  # CalibratedClassifierCV


def make_version_string(name: str, major: int = 1, minor: int = 0, patch: int = 0) -> str:
    """Generate model version string."""
    today = datetime.now(timezone.utc).date().isoformat()
    return f"{name}_{major}.{minor}.{patch}_{today}"


@dataclass
class WalkForwardWindow:
    """One walk-forward train/val/test window."""

    train_start: date
    train_end: date
    val_start: date
    val_end: date
    test_start: date
    test_end: date


def build_walk_forward_schedule(
    history_start: date,
    history_end: date,
    n_steps: int = 8,
    train_months: int = 24,
    val_months: int = 6,
    test_months: int = 6,
    embargo_days: int = 5,
) -> list[WalkForwardWindow]:
    """Build a walk-forward schedule.

    Each step shifts by `(history_end - history_start) / (n_steps + train+val+test+embargo)`
    """
    days_per_month = 30
    train_days = train_months * days_per_month
    val_days = val_months * days_per_month
    test_days = test_months * days_per_month
    needed_days = train_days + val_days + test_days + 2 * embargo_days

    available_days = (history_end - history_start).days
    if available_days < needed_days:
        raise ValueError(
            f"Need {needed_days} days, have {available_days}. "
            f"Reduce window sizes or n_steps."
        )

    step_days = (available_days - needed_days) // max(1, n_steps - 1)

    windows = []
    for i in range(n_steps):
        offset = timedelta(days=i * step_days)
        train_s = history_start + offset
        train_e = train_s + timedelta(days=train_days)
        val_s = train_e + timedelta(days=embargo_days)
        val_e = val_s + timedelta(days=val_days)
        test_s = val_e + timedelta(days=embargo_days)
        test_e = test_s + timedelta(days=test_days)
        if test_e > history_end:
            break
        windows.append(WalkForwardWindow(train_s, train_e, val_s, val_e, test_s, test_e))

    return windows


def progressive_training_stages(
    history_start: date,
    history_end: date,
    n_stages: int = 5,
) -> list[WalkForwardWindow]:
    """Progressive training: train window grows by 6 months each stage.

    From v7 §N. Stage 1 uses 2 years; each subsequent stage adds 6 months.
    """
    stages = []
    base_train_months = 24

    for stage in range(n_stages):
        train_months = base_train_months + stage * 6
        train_days = train_months * 30
        val_days = 180
        test_days = 180
        embargo_days = 5

        train_s = history_start
        train_e = train_s + timedelta(days=train_days)
        val_s = train_e + timedelta(days=embargo_days)
        val_e = val_s + timedelta(days=val_days)
        test_s = val_e + timedelta(days=embargo_days)
        test_e = test_s + timedelta(days=test_days)

        if test_e > history_end:
            break

        stages.append(WalkForwardWindow(train_s, train_e, val_s, val_e, test_s, test_e))

    return stages


def save_model_artifact(artifact: ModelArtifact, output_dir: Path) -> Path:
    """Save model artifact to disk.

    Layout: /data/models/<name>/<version>/
       ├── model.lgb
       ├── calibrator.pkl
       ├── manifest.json
       ├── features.json
       └── metrics.json
    """
    target_dir = output_dir / artifact.name / artifact.version
    target_dir.mkdir(parents=True, exist_ok=True)

    # Save model (placeholder — real version uses booster.save_model())
    if artifact.booster is not None:
        try:
            artifact.booster.save_model(str(target_dir / "model.lgb"))
        except Exception as e:
            logger.warning("save_booster_failed", error=str(e))

    # Save calibrator
    if artifact.calibrator is not None:
        try:
            import pickle
            with open(target_dir / "calibrator.pkl", "wb") as f:
                pickle.dump(artifact.calibrator, f)
        except Exception as e:
            logger.warning("save_calibrator_failed", error=str(e))

    # Save metadata
    manifest = {
        "name": artifact.name,
        "version": artifact.version,
        "horizon": artifact.horizon,
        "target": artifact.target,
        "trained_at": artifact.trained_at.isoformat(),
        "train_window_start": artifact.train_window_start.isoformat(),
        "train_window_end": artifact.train_window_end.isoformat(),
        "feature_set_version": artifact.feature_set_version,
        "parent_version": artifact.parent_version,
        "state": artifact.state,
    }
    with open(target_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    with open(target_dir / "metrics.json", "w") as f:
        json.dump(artifact.metrics, f, indent=2, default=str)

    artifact.artifact_path = target_dir
    logger.info(
        "model_saved",
        name=artifact.name,
        version=artifact.version,
        path=str(target_dir),
    )
    return target_dir


def load_model_artifact(artifact_path: Path) -> ModelArtifact:
    """Load a saved model artifact from disk."""
    with open(artifact_path / "manifest.json") as f:
        manifest = json.load(f)

    metrics_path = artifact_path / "metrics.json"
    metrics = {}
    if metrics_path.exists():
        with open(metrics_path) as f:
            metrics = json.load(f)

    artifact = ModelArtifact(
        name=manifest["name"],
        version=manifest["version"],
        horizon=manifest["horizon"],
        target=manifest["target"],
        trained_at=datetime.fromisoformat(manifest["trained_at"]),
        train_window_start=date.fromisoformat(manifest["train_window_start"]),
        train_window_end=date.fromisoformat(manifest["train_window_end"]),
        feature_set_version=manifest["feature_set_version"],
        artifact_path=artifact_path,
        parent_version=manifest.get("parent_version"),
        state=manifest.get("state", "CANDIDATE"),
        metrics=metrics,
    )

    # Load booster
    booster_path = artifact_path / "model.lgb"
    if booster_path.exists():
        try:
            import lightgbm as lgb
            artifact.booster = lgb.Booster(model_file=str(booster_path))
        except Exception as e:
            logger.warning("load_booster_failed", error=str(e))

    # Load calibrator
    calibrator_path = artifact_path / "calibrator.pkl"
    if calibrator_path.exists():
        try:
            import pickle
            with open(calibrator_path, "rb") as f:
                artifact.calibrator = pickle.load(f)
        except Exception as e:
            logger.warning("load_calibrator_failed", error=str(e))

    return artifact
