"""Remote control + self-update for store agents.

Two routers, deliberately on different prefixes:
  * ``agent_router`` (prefix ``/agent/watchdog``) is what the unattended
    watchdog service on each store PC talks to. It sits under ``/agent/*``,
    which the auth middleware in api/app.py never gates (same reason
    ``/agent/tasks/poll`` etc. are public - there is no user/JWT on a store
    machine).
  * ``router`` (prefix ``/api/agent-ops``) is the admin surface the HO
    frontend calls. It starts with ``/api/`` so the existing auth middleware
    already requires a Bearer token for it - no extra wiring needed here.
"""
from fastapi import APIRouter
from fastapi.responses import FileResponse

from modules.agent_ops import service
from modules.agent_ops.schemas import (
    BulkVersionRequest,
    BulkStateRequest,
    HeartbeatRequest,
    SetStateRequest,
    SetVersionRequest,
)

agent_router = APIRouter(prefix="/agent/watchdog", tags=["Agent Watchdog"])
router = APIRouter(prefix="/api/agent-ops", tags=["Agent Ops"])


@agent_router.get("/state/{store_id}")
def watchdog_state(store_id: str):
    return service.get_watchdog_state(store_id)


@agent_router.post("/heartbeat")
def watchdog_heartbeat(payload: HeartbeatRequest):
    return service.record_heartbeat(payload)


@agent_router.get("/download/{version}")
def watchdog_download(version: str):
    path, file_name = service.download_path(version)
    return FileResponse(path, filename=file_name, media_type="application/octet-stream")


@router.get("/stores")
def list_stores(tenant_id: str | None = None):
    return service.list_stores(tenant_id)


@router.post("/stores/{store_id}/state")
def set_state(store_id: str, payload: SetStateRequest):
    return service.set_state(store_id, payload.desired_state)


@router.post("/stores/state-bulk")
def set_state_bulk(payload: BulkStateRequest):
    return service.set_state_bulk(payload.store_ids, payload.desired_state)


@router.get("/releases")
def list_releases():
    return service.list_releases()


@router.get("/logs")
def list_logs(limit: int = 100, store_id: str | None = None):
    return service.list_logs(limit=limit, store_id=store_id)


@router.post("/stores/{store_id}/version")
def set_version(store_id: str, payload: SetVersionRequest):
    return service.set_version(store_id, payload.desired_version)


@router.post("/stores/version-bulk")
def set_version_bulk(payload: BulkVersionRequest):
    return service.set_version_bulk(payload.store_ids, payload.desired_version)
