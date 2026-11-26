"""Admin 'Live Queries / Repair' page: see what's running on central OrderNMC
right now and kill a stuck session. Platform-admin only, same gate as the
Legacy Order console (modules.legacy_order.router.require_admin)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies.auth import get_current_user
from dependencies.store_scope import has_unrestricted_scope
from modules.db_monitor import service

router = APIRouter(prefix="/api/db-monitor", tags=["db-monitor"])


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not has_unrestricted_scope(current_user):
        raise HTTPException(status_code=403, detail="Live Queries is restricted to platform admins.")
    return current_user


class KillSessionRequest(BaseModel):
    session_id: int


@router.get("/requests")
def get_active_requests(current_user: dict = Depends(require_admin)):
    try:
        return {"requests": service.active_requests()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/sessions")
def get_all_sessions(current_user: dict = Depends(require_admin)):
    try:
        return {"sessions": service.all_sessions()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/kill")
def post_kill_session(payload: KillSessionRequest, current_user: dict = Depends(require_admin)):
    try:
        return service.kill_session(payload.session_id, actor=current_user.get("username"))
    except (service.InvalidSessionId, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
