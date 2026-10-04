"""Request bodies for Stock Client fleet management.

Responses are plain dicts straight from the repository (same style as
modules/agent_ops), so only inbound payloads are modelled here.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


# ---- admin (HO super-admin) ----------------------------------------------

class DeploymentCreateRequest(BaseModel):
    release_id: str = Field(..., description="stock_client_releases.id (PK) of an APPROVED release")
    scope: str = Field(..., pattern="^(ALL|SELECTED)$")
    store_ids: List[str] = Field(default_factory=list,
                                 description="required when scope=SELECTED; ignored for ALL")


# ---- agent (device-token) -------------------------------------------------

class InstallationRegisterRequest(BaseModel):
    installation_id: str = Field(..., min_length=8, max_length=60)
    fingerprint_hash: Optional[str] = Field(None, max_length=200)
    hostname: Optional[str] = Field(None, max_length=200)
    os_version: Optional[str] = Field(None, max_length=200)
    client_version: Optional[str] = Field(None, max_length=50)


class StockClientHeartbeatRequest(BaseModel):
    installation_id: str = Field(..., min_length=8, max_length=60)
    watchdog_version: Optional[str] = Field(None, max_length=50)
    watchdog_status: Optional[str] = Field(None, max_length=20)
    client_status: Optional[str] = Field(None, max_length=20)      # RUNNING|STOPPED|UNKNOWN
    client_version: Optional[str] = Field(None, max_length=50)
    local_ip: Optional[str] = Field(None, max_length=60)
    os_version: Optional[str] = Field(None, max_length=200)
    last_update_status: Optional[str] = Field(None, max_length=30)
    last_error: Optional[str] = Field(None, max_length=1000)
    # Optional per-update progress the watchdog is driving for its store.
    target_version: Optional[str] = Field(None, max_length=50)
    target_status: Optional[str] = Field(None, max_length=20)
    target_progress: Optional[int] = Field(None, ge=0, le=100)
    target_error: Optional[str] = Field(None, max_length=1000)
