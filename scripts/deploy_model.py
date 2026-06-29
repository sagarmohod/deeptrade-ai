"""Deploy a trained model — register in DB and optionally rsync to VPS.

Usage:
    python scripts/deploy_model.py --name meta_scalp --version 1.0.0_2026-05-04

After running this:
    - Model artifact is registered in model_registry table (state=CANDIDATE)
    - To activate: POST /api/v1/models/<name>/<version>/activate (or via UI)
    - Optionally pushes to VPS if --target=vps and SSH credentials configured
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
from pathlib import Path

import structlog

from core.ml import ModelRegistry, load_model_artifact

logger = structlog.get_logger(__name__)


async def deploy_model(
    name: str,
    version: str,
    models_dir: Path,
    target: str = "local",
    vps_host: str | None = None,
) -> None:
    """Deploy a model: register in DB + optionally rsync to VPS."""
    artifact_path = models_dir / name / version
    if not artifact_path.exists():
        raise FileNotFoundError(f"Artifact not found: {artifact_path}")

    artifact = load_model_artifact(artifact_path)
    logger.info("loaded_artifact", name=name, version=version)

    # Register in DB
    registry = ModelRegistry(models_dir)
    await registry.register(artifact, state="CANDIDATE")
    logger.info("registered_in_db", state="CANDIDATE")

    # Push to VPS if configured
    if target == "vps" and vps_host:
        cmd = [
            "rsync",
            "-avz",
            "--progress",
            f"{artifact_path}/",
            f"{vps_host}:/opt/deeptrade/models/{name}/{version}/",
        ]
        logger.info("rsync_starting", cmd=" ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("rsync_failed", stderr=result.stderr)
            raise RuntimeError(f"rsync failed: {result.stderr}")
        logger.info("rsync_complete")

    print()
    print(f"✓ Model {name} v{version} deployed (state=CANDIDATE)")
    print(f"  To activate: POST /api/v1/models/{name}/{version}/activate")
    print(f"  Or via UI:   Models → {name} → Activate v{version}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--models-dir", default="./models")
    parser.add_argument("--target", choices=["local", "vps"], default="local")
    parser.add_argument("--vps-host", help="user@host for rsync (only if target=vps)")
    args = parser.parse_args()

    asyncio.run(deploy_model(
        args.name, args.version, Path(args.models_dir),
        args.target, args.vps_host,
    ))


if __name__ == "__main__":
    main()
