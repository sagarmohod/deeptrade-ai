"""Model registry — tracks model lifecycle states (v3 §H)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import structlog
from sqlalchemy import select

from core.db import ModelRegistryRow, get_session
from core.ml.training import ModelArtifact, load_model_artifact

logger = structlog.get_logger(__name__)

# Lifecycle states
STATES = ["TRAINING", "CANDIDATE", "SHADOW", "ACTIVE", "DEPRECATED", "FAILED", "ARCHIVED"]


class ModelRegistry:
    """Tracks all model versions and their lifecycle states."""

    def __init__(self, models_dir: Path | str) -> None:
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    async def register(
        self,
        artifact: ModelArtifact,
        state: str = "CANDIDATE",
    ) -> None:
        """Register a new model version."""
        async with get_session() as session:
            row = ModelRegistryRow(
                name=artifact.name,
                version=artifact.version,
                horizon=artifact.horizon,
                target=artifact.target,
                trained_at=artifact.trained_at,
                train_window_start=artifact.train_window_start,
                train_window_end=artifact.train_window_end,
                metrics=artifact.metrics,
                artifact_path=str(artifact.artifact_path),
                feature_set_version=artifact.feature_set_version,
                state=state,
                parent_version=artifact.parent_version,
            )
            session.add(row)
        logger.info("model_registered", name=artifact.name, version=artifact.version, state=state)

    async def get_active(self, name: str) -> ModelArtifact | None:
        """Get the currently ACTIVE model for a name."""
        async with get_session() as session:
            stmt = select(ModelRegistryRow).where(
                ModelRegistryRow.name == name,
                ModelRegistryRow.state == "ACTIVE",
                ModelRegistryRow.is_active.is_(True),
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            return None

        try:
            return load_model_artifact(Path(row.artifact_path))
        except Exception as e:
            logger.error("load_active_model_failed", name=name, error=str(e))
            return None

    async def set_state(self, name: str, version: str, state: str, reason: str = "") -> None:
        """Update lifecycle state."""
        async with get_session() as session:
            stmt = select(ModelRegistryRow).where(
                ModelRegistryRow.name == name,
                ModelRegistryRow.version == version,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                raise ValueError(f"Model not found: {name}/{version}")

            row.state = state
            if state == "ACTIVE":
                row.is_active = True
                row.activated_at = datetime.utcnow()
            elif state == "DEPRECATED":
                row.is_active = False
                row.deactivated_at = datetime.utcnow()
                row.deprecation_reason = reason

        logger.info("model_state_changed", name=name, version=version, state=state)

    async def activate(self, name: str, version: str) -> None:
        """Activate a model — deactivates any currently active one."""
        async with get_session() as session:
            # Deactivate current
            stmt = select(ModelRegistryRow).where(
                ModelRegistryRow.name == name,
                ModelRegistryRow.is_active.is_(True),
            )
            result = await session.execute(stmt)
            for row in result.scalars():
                row.is_active = False
                row.state = "DEPRECATED"
                row.deactivated_at = datetime.utcnow()
                row.deprecation_reason = f"replaced_by_{version}"

            # Activate new
            stmt = select(ModelRegistryRow).where(
                ModelRegistryRow.name == name,
                ModelRegistryRow.version == version,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"Model not found: {name}/{version}")

            row.state = "ACTIVE"
            row.is_active = True
            row.activated_at = datetime.utcnow()

        logger.info("model_activated", name=name, version=version)

    async def list_versions(self, name: str | None = None) -> list[dict]:
        """List all model versions, optionally filtered by name."""
        async with get_session() as session:
            stmt = select(ModelRegistryRow)
            if name:
                stmt = stmt.where(ModelRegistryRow.name == name)
            stmt = stmt.order_by(ModelRegistryRow.trained_at.desc())
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            {
                "name": r.name,
                "version": r.version,
                "state": r.state,
                "is_active": r.is_active,
                "trained_at": r.trained_at.isoformat() if r.trained_at else None,
                "metrics": r.metrics,
                "horizon": r.horizon,
            }
            for r in rows
        ]

    async def rollback(self, name: str, target_version: str | None = None) -> None:
        """Rollback to previous active version, or specified version."""
        async with get_session() as session:
            if target_version:
                stmt = select(ModelRegistryRow).where(
                    ModelRegistryRow.name == name,
                    ModelRegistryRow.version == target_version,
                )
            else:
                # Most recent DEPRECATED
                stmt = (
                    select(ModelRegistryRow)
                    .where(
                        ModelRegistryRow.name == name,
                        ModelRegistryRow.state == "DEPRECATED",
                    )
                    .order_by(ModelRegistryRow.deactivated_at.desc())
                    .limit(1)
                )
            result = await session.execute(stmt)
            target = result.scalar_one_or_none()
            if target is None:
                raise ValueError(f"No rollback target found for {name}")

        await self.activate(name, target.version)
        logger.info("model_rollback", name=name, version=target.version)
