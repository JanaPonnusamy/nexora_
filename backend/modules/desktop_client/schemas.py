"""Request/response shapes for managed desktop clients."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ActivateRequest(BaseModel):
    device_fingerprint: str = Field(..., min_length=1, max_length=200)
    machine_name: Optional[str] = Field(None, max_length=200)
    app_version: Optional[str] = Field(None, max_length=50)
    requested_store_name: Optional[str] = Field(None, max_length=200)
    requested_store_code: Optional[str] = Field(None, max_length=50)
    install_code: Optional[str] = Field(None, max_length=100)


class ActivateResponse(BaseModel):
    client_id: str
    status: str


class ConfigResponse(BaseModel):
    client_id: Optional[str] = None
    status: str
    tenant_id: Optional[str] = None
    store_id: Optional[str] = None
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    server_base_url: Optional[str] = None
    latest_version: Optional[str] = None
    min_version: Optional[str] = None
    update_url: Optional[str] = None
    force_update: bool = False
    maintenance_message: Optional[str] = None


class HeartbeatRequest(BaseModel):
    client_id: str
    app_version: Optional[str] = Field(None, max_length=50)


class HeartbeatResponse(BaseModel):
    client_id: str
    status: str


class DeviceOut(BaseModel):
    client_id: str
    device_fingerprint: str
    machine_name: Optional[str] = None
    app_version: Optional[str] = None
    status: str
    tenant_id: Optional[str] = None
    store_id: Optional[str] = None
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    server_base_url: Optional[str] = None
    enabled: bool
    requested_store_name: Optional[str] = None
    requested_store_code: Optional[str] = None
    install_code: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DeviceListResponse(BaseModel):
    devices: List[DeviceOut] = []


class DeviceApproveRequest(BaseModel):
    tenant_id: str
    store_id: str
    store_code: Optional[str] = Field(None, max_length=50)
    store_name: Optional[str] = Field(None, max_length=200)
    server_base_url: Optional[str] = Field(None, max_length=500)
    enabled: bool = True
