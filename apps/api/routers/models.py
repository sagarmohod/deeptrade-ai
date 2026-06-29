"""Models router — model registry endpoints."""
from __future__ import annotations
from pathlib import Path
from fastapi import APIRouter, HTTPException
from core.ml import ModelRegistry

router = APIRouter()
_registry = ModelRegistry(Path("./models"))


@router.get("/")
async def list_models(name: str | None = None) -> dict:
    """List all model versions."""
    versions = await _registry.list_versions(name)
    return {"models": versions}


@router.post("/{name}/{version}/activate")
async def activate_model(name: str, version: str) -> dict:
    """Activate a specific model version."""
    try:
        await _registry.activate(name, version)
        return {"ok": True, "message": f"{name} v{version} is now active"}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{name}/rollback")
async def rollback_model(name: str) -> dict:
    """Rollback to previous active version."""
    try:
        await _registry.rollback(name)
        return {"ok": True, "message": f"{name} rolled back"}
    except ValueError as e:
        raise HTTPException(404, str(e))
