from __future__ import annotations

"""Request/response models for the mobile BFF."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DeviceInfo(BaseModel):
    """Identifies the calling device. `device_id` is minted and persisted on the
    phone (see mobile/docs/API_CONTRACT.md — device registration is local-only),
    and binds a refresh-token chain to one install."""

    device_id: str = Field(min_length=8, max_length=200)
    device_name: Optional[str] = Field(default=None, max_length=200)
    platform: Optional[str] = Field(default=None, max_length=30)
    app_version: Optional[str] = Field(default=None, max_length=50)


class MobileLoginRequest(BaseModel):
    username: str
    password: str
    device: DeviceInfo


class RefreshRequest(BaseModel):
    refresh_token: str
    device_id: str = Field(min_length=8, max_length=200)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None
    device_id: Optional[str] = None
    all_devices: bool = False


class TokenPair(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str
    refresh_expires_in: int
    user: Optional[Dict[str, Any]] = None


class HandshakeResponse(BaseModel):
    """Lets a shipped binary decide whether it can talk to this server before it
    tries. `GET /health` returns only {"status":"healthy"} and carries no
    version, so there was previously no way to detect an incompatible pairing."""

    api_version: str
    min_supported_build: int
    latest_build: int
    server_time: str
    features: List[str]


class DashboardResponse(BaseModel):
    user: Dict[str, Any]
    store: Optional[Dict[str, Any]] = None
    sync: Optional[Dict[str, Any]] = None
    documents: Optional[Dict[str, Any]] = None
    procurement: Optional[Dict[str, Any]] = None
    generated_at: str
