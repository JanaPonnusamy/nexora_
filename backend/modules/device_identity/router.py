"""Device identity endpoints.

Public:   POST /api/auth/device/token   (signature-authenticated; no bearer yet)
Login:    POST /api/auth/device/register (store-user Bearer authorizes the machine)
Device:   GET  /api/agent/stores         (device Bearer -> assigned stores + config)
          POST /api/agent/heartbeat
Admin:    GET  /api/devices, POST /api/devices/{id}/stores,
          DELETE /api/devices/{id}/stores/{store_id}, POST /api/devices/{id}/revoke
"""
from __future__ import annotations

import time

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from config.security import create_access_token, decode_access_token
from dependencies.auth import get_current_user
from dependencies.store_scope import require_super_admin
from modules.device_identity import crypto
from modules.device_identity import repository as repo

# Reject a signed challenge whose timestamp is off by more than this, to bound
# replay of a captured signature.
_MAX_CLOCK_SKEW_SECONDS = 300

auth_router = APIRouter(prefix="/api/auth/device", tags=["Device Identity"])
agent_router = APIRouter(prefix="/api/agent", tags=["Device Identity"])
admin_router = APIRouter(prefix="/api/devices", tags=["Device Identity"])


# ---- schemas --------------------------------------------------------------

class RegisterRequest(BaseModel):
    device_fingerprint: str = Field(..., min_length=1, max_length=200)
    public_key: str = Field(..., min_length=1)
    key_algo: str = Field("ED25519", max_length=30)
    machine_name: str | None = Field(None, max_length=200)
    app_type: str | None = Field(None, max_length=30)
    app_version: str | None = Field(None, max_length=50)


class TokenRequest(BaseModel):
    device_id: str = Field(..., min_length=1)
    timestamp: str = Field(..., description="Unix epoch seconds, as a string")
    nonce: str = Field(..., min_length=1, max_length=200)
    signature: str = Field(..., description="Base64 (standard) Ed25519 signature")


class AssignRequest(BaseModel):
    store_id: str = Field(..., min_length=1)


# ---- device auth dependency ----------------------------------------------

def get_current_device(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization[7:].strip()
    try:
        claims = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if claims.get("token_kind") != "device":
        raise HTTPException(status_code=403, detail="Device token required")
    device = repo.get_device(claims.get("device_id"))
    if not device or device["status"] != "active":
        raise HTTPException(status_code=403, detail="Device is not registered or has been revoked")
    return claims


# ---- registration (store-user authorizes the machine) ---------------------

@auth_router.post("/register")
def register(body: RegisterRequest, user: dict = Depends(get_current_user)):
    """A store user (created in HO, assigned to a tenant+store) signs in once on
    the machine; this registers the machine's public key + fingerprint and, as a
    convenience, auto-assigns that user's own store so the agent works
    immediately. Super admins assign further stores from HO."""
    device_id, is_new = repo.register_device(
        body.device_fingerprint, body.public_key, body.key_algo,
        body.machine_name, body.app_type, body.app_version, user,
    )
    return {
        "device_id": device_id,
        "is_new": is_new,
        "assigned_store_ids": repo.get_assigned_store_ids(device_id),
    }


# ---- token issuance (signature-authenticated, public) ---------------------

@auth_router.post("/token")
def issue_token(body: TokenRequest):
    """The device proves possession of its private key by signing
    `<device_id>.<timestamp>.<nonce>`; on success it gets a short-lived access
    token scoped to its assigned stores. Public: the device has no bearer yet."""
    import base64

    device = repo.get_device(body.device_id)
    if not device or device["status"] != "active":
        raise HTTPException(status_code=403, detail="Device is not registered or has been revoked")

    try:
        ts = float(body.timestamp)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid timestamp")
    if abs(time.time() - ts) > _MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Challenge timestamp outside the allowed window")

    try:
        signature = base64.b64decode(body.signature)
    except Exception:
        raise HTTPException(status_code=400, detail="Signature is not valid base64")

    message = crypto.canonical_message(body.device_id, body.timestamp, body.nonce)
    if not crypto.verify(device["public_key"], message, signature):
        raise HTTPException(status_code=401, detail="Signature verification failed")

    stores = repo.get_assigned_stores_with_config(body.device_id)
    store_ids = [s["store_id"] for s in stores]
    tenant_ids = sorted({s["tenant_id"] for s in stores if s["tenant_id"]})
    repo.touch_last_seen(body.device_id)

    # Device tokens carry no `sid`, so they are exempt from the single-session
    # policy (a store PC reboot must never lock itself out).
    token = create_access_token({
        "sub": body.device_id,
        "token_kind": "device",
        "device_id": body.device_id,
        "app_type": device["app_type"],
        "store_ids": store_ids,
        "tenant_ids": tenant_ids,
    })
    return {"token": token, "token_type": "bearer", "store_ids": store_ids}


# ---- agent (device token) -------------------------------------------------

@agent_router.get("/stores")
def get_my_stores(device: dict = Depends(get_current_device)):
    """Every store assigned to the calling device, each with its DB connection
    (agent-config). The multi-store agent pulls this each cycle so credential
    changes / added / removed stores are picked up automatically."""
    return {"stores": repo.get_assigned_stores_with_config(device["device_id"])}


class AgentHeartbeat(BaseModel):
    app_version: str | None = Field(None, max_length=50)


@agent_router.post("/heartbeat")
def agent_heartbeat(body: AgentHeartbeat, device: dict = Depends(get_current_device)):
    repo.touch_last_seen(device["device_id"], body.app_version)
    return {"device_id": device["device_id"], "status": "ok"}


# ---- admin (super-admin) --------------------------------------------------

@admin_router.get("")
def list_devices(_: dict = Depends(require_super_admin)):
    return {"devices": repo.list_devices()}


@admin_router.post("/{device_id}/stores")
def assign_store(device_id: str, body: AssignRequest, user: dict = Depends(require_super_admin)):
    device = repo.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    from services.store_service import StoreService
    store = StoreService().get_by_id(body.store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    tenant_id = str(store[1]) if store[1] else None
    repo.assign_store(device_id, body.store_id, tenant_id, user.get("sub"))
    return {"device_id": device_id, "stores": repo.get_assigned_store_ids(device_id)}


@admin_router.delete("/{device_id}/stores/{store_id}")
def unassign_store(device_id: str, store_id: str, _: dict = Depends(require_super_admin)):
    repo.unassign_store(device_id, store_id)
    return {"device_id": device_id, "stores": repo.get_assigned_store_ids(device_id)}


@admin_router.post("/{device_id}/revoke")
def revoke(device_id: str, _: dict = Depends(require_super_admin)):
    affected = repo.revoke_device(device_id)
    if not affected:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"device_id": device_id, "status": "revoked"}
