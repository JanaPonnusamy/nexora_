"""Managed desktop client APIs for future Electron clients."""

from typing import Optional

from fastapi import APIRouter, Query

from modules.desktop_client import service
from modules.desktop_client.schemas import (
    ActivateRequest,
    ActivateResponse,
    ConfigResponse,
    DeviceApproveRequest,
    DeviceListResponse,
    DeviceOut,
    HeartbeatRequest,
    HeartbeatResponse,
)

router = APIRouter(prefix="/api/desktop-client", tags=["Desktop Client"])


@router.post("/activate/request", response_model=ActivateResponse)
def activate_request(payload: ActivateRequest):
    return service.activate(payload)


@router.get("/config", response_model=ConfigResponse)
def get_config(
    client_id: str = Query(...),
    app_version: Optional[str] = Query(None),
):
    return service.config(client_id, app_version)


@router.post("/heartbeat", response_model=HeartbeatResponse)
def heartbeat(payload: HeartbeatRequest):
    return service.heartbeat(payload)


@router.get("/devices", response_model=DeviceListResponse)
def list_devices():
    return service.list_devices()


@router.post("/devices/{client_id}/approve", response_model=DeviceOut)
def approve_device(client_id: str, payload: DeviceApproveRequest):
    return service.approve(client_id, payload)
