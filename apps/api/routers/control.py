"""Control router — kill switch, mode switching."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# In-memory state (would be Redis-backed in production)
_kill_switch_state = {"active": False, "activated_at": None, "reason": None}


class KillSwitchRequest(BaseModel):
    confirmation: str  # must equal "KILL_ALL"
    reason: str = "manual"


@router.post("/kill")
async def activate_kill_switch(req: KillSwitchRequest) -> dict:
    """Activate kill switch — cancel all orders, flatten positions."""
    if req.confirmation != "KILL_ALL":
        raise HTTPException(400, "Confirmation must be 'KILL_ALL'")

    from datetime import datetime
    _kill_switch_state["active"] = True
    _kill_switch_state["activated_at"] = datetime.utcnow().isoformat()
    _kill_switch_state["reason"] = req.reason

    # In production: cancel all open orders, flatten positions
    return {
        "ok": True,
        "message": "Kill switch activated. All trading halted.",
        "state": _kill_switch_state,
    }


@router.post("/kill/reset")
async def reset_kill_switch() -> dict:
    """Reset kill switch (manual)."""
    _kill_switch_state["active"] = False
    _kill_switch_state["activated_at"] = None
    _kill_switch_state["reason"] = None
    return {"ok": True, "message": "Kill switch reset"}


@router.get("/kill/status")
async def kill_switch_status() -> dict:
    """Current kill switch state."""
    return _kill_switch_state
