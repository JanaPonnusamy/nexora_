"""Stock Client fleet-management APIs.

Two routers:
  * ``router`` (/api/stock-client-ops) - the HO admin surface, super-admin only.
    Release approval, authorized per-store rollouts, and the monitor dashboard.
  * ``agent_router`` (/api/agent/stock-client) - what the on-store watchdog
    (device token, app_type='stock_client') calls: register, poll state,
    download the signed package, heartbeat. Device-token auth is reused from
    modules.device_identity (no second auth system).
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from dependencies.store_scope import require_super_admin
from modules.device_identity.router import get_current_device
from modules.stock_client_ops import service
from modules.stock_client_ops.schemas import (
    DeploymentCreateRequest,
    InstallationRegisterRequest,
    StockClientHeartbeatRequest,
)

router = APIRouter(prefix="/api/stock-client-ops", tags=["Stock Client Ops"])
agent_router = APIRouter(prefix="/api/agent/stock-client", tags=["Stock Client Agent"])


def _actor(user: dict) -> str:
    return str(user.get("username") or user.get("sub") or "")


# ---- admin: releases ------------------------------------------------------

@router.get("/releases")
def list_releases(_: dict = Depends(require_super_admin)):
    return service.list_releases()


@router.post("/releases/{release_id}/approve")
def approve_release(release_id: str, user: dict = Depends(require_super_admin)):
    return service.approve_release(release_id, actor=_actor(user))


@router.post("/releases/{release_id}/retire")
def retire_release(release_id: str, user: dict = Depends(require_super_admin)):
    return service.retire_release(release_id, actor=_actor(user))


# ---- admin: deployments (rollouts) ---------------------------------------

@router.get("/deployments")
def list_deployments(_: dict = Depends(require_super_admin)):
    return service.list_deployments()


@router.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: str, _: dict = Depends(require_super_admin)):
    return service.get_deployment(deployment_id)


@router.post("/deployments")
def create_deployment(payload: DeploymentCreateRequest, user: dict = Depends(require_super_admin)):
    return service.create_deployment(payload, actor=_actor(user))


@router.post("/deployments/{deployment_id}/authorize")
def authorize_deployment(deployment_id: str, user: dict = Depends(require_super_admin)):
    return service.authorize_deployment(deployment_id, actor=_actor(user))


@router.post("/deployments/{deployment_id}/cancel")
def cancel_deployment(deployment_id: str, user: dict = Depends(require_super_admin)):
    return service.cancel_deployment(deployment_id, actor=_actor(user))


@router.post("/deployments/{deployment_id}/targets/{target_id}/retry")
def retry_target(deployment_id: str, target_id: str, user: dict = Depends(require_super_admin)):
    return service.retry_target(deployment_id, target_id, actor=_actor(user))


# ---- admin: monitoring ----------------------------------------------------

@router.get("/installations")
def list_installations(_: dict = Depends(require_super_admin)):
    return service.list_installations()


@router.get("/installations/{installation_id}")
def get_installation(installation_id: str, _: dict = Depends(require_super_admin)):
    return service.get_installation(installation_id)


# ---- agent (device token) -------------------------------------------------

@agent_router.post("/installations/register")
def register_installation(payload: InstallationRegisterRequest,
                          device: dict = Depends(get_current_device)):
    return service.register_installation(payload, device)


@agent_router.get("/state")
def get_state(installation_id: str, device: dict = Depends(get_current_device)):
    return service.get_state(installation_id)


@agent_router.post("/heartbeat")
def heartbeat(payload: StockClientHeartbeatRequest, request: Request,
              device: dict = Depends(get_current_device)):
    observed_ip = request.client.host if request.client else None
    return service.record_heartbeat(payload, observed_ip=observed_ip)


@agent_router.get("/download/{version}")
def download(version: str, device: dict = Depends(get_current_device)):
    path, file_name = service.download_path(version)
    return FileResponse(path, filename=file_name, media_type="application/octet-stream")
