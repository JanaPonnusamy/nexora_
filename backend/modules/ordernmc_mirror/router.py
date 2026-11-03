"""OrderNMC mirror endpoints.

Agent (device Bearer, see device_identity):
  GET  /api/ordernmc-mirror/v1/agent/config   target DB connection + interval
  POST /api/ordernmc-mirror/v1/agent/pull     next batch | progress | idle
  POST /api/ordernmc-mirror/v1/agent/ack      batch applied (or failed)
Admin (super-admin):
  GET    /api/ordernmc-mirror/v1/admin/sources
  GET    /api/ordernmc-mirror/v1/admin/targets
  PUT    /api/ordernmc-mirror/v1/admin/targets            (by device_id)
  GET    /api/ordernmc-mirror/v1/admin/targets/{id}/status
  POST   /api/ordernmc-mirror/v1/admin/targets/{id}/reset
  DELETE /api/ordernmc-mirror/v1/admin/targets/{id}
"""
from __future__ import annotations

import gzip
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from dependencies.store_scope import require_super_admin
from modules.device_identity import repository as device_repo
from modules.device_identity.router import get_current_device
from modules.ordernmc_mirror import repository as repo, service, sources

_logger = logging.getLogger(__name__)

agent_router = APIRouter(prefix="/api/ordernmc-mirror/v1/agent", tags=["OrderNMC Mirror"])
admin_router = APIRouter(prefix="/api/ordernmc-mirror/v1/admin", tags=["OrderNMC Mirror"])


class AckRequest(BaseModel):
    batch_id: str = Field(..., min_length=1, max_length=64)
    ok: bool = True
    error: str | None = Field(None, max_length=4000)


class TargetRequest(BaseModel):
    device_id: str = Field(..., min_length=1)
    source_name: str = Field(sources.DEFAULT_SOURCE, min_length=1, max_length=50)
    server_name: str = Field(..., min_length=1, max_length=200)
    database_name: str = Field("OrderNMC", min_length=1, max_length=128)
    username: str | None = Field(None, max_length=128)
    password: str | None = Field(None, description="Blank keeps the stored password")
    interval_seconds: int = Field(900, ge=60, le=86400)
    tables: str | None = Field(None, description="Optional comma-separated whitelist (* wildcards)")
    is_enabled: bool = True


class ResetRequest(BaseModel):
    tables: list[str] | None = None


def _json(request: Request, payload) -> Response:
    """JSON, gzipped when the client accepts it (batches are large)."""
    body = json.dumps(payload, default=str, separators=(",", ":")).encode("utf-8")
    if "gzip" in (request.headers.get("accept-encoding") or "").lower() and len(body) > 1024:
        return Response(gzip.compress(body, 6), media_type="application/json",
                        headers={"Content-Encoding": "gzip"})
    return Response(body, media_type="application/json")


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.MirrorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown mirror source {exc}")


# ---- agent ----------------------------------------------------------------

@agent_router.get("/config")
def agent_config(device: dict = Depends(get_current_device)):
    return _call(service.agent_config, device["device_id"])


@agent_router.post("/pull")
async def agent_pull(request: Request, device: dict = Depends(get_current_device)):
    try:
        payload = await run_in_threadpool(_call, service.pull, device["device_id"])
    except HTTPException:
        raise
    except Exception as exc:
        _logger.exception("ordernmc mirror pull failed")
        raise HTTPException(status_code=503, detail=f"Mirror source unavailable: {exc}")
    return _json(request, payload)


@agent_router.post("/ack")
def agent_ack(body: AckRequest, device: dict = Depends(get_current_device)):
    return _call(service.ack, device["device_id"], body.batch_id, body.ok, body.error)


# ---- admin ----------------------------------------------------------------

@admin_router.get("/sources")
def list_sources(_: dict = Depends(require_super_admin)):
    return {"sources": [sources.describe(n) for n in sources.source_names()]}


@admin_router.get("/targets")
def list_targets(_: dict = Depends(require_super_admin)):
    return {"targets": [service.public_target(t) for t in repo.list_targets()]}


@admin_router.put("/targets")
def put_target(body: TargetRequest, _: dict = Depends(require_super_admin)):
    if not device_repo.get_device(body.device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    if body.source_name.lower() not in sources.source_names():
        raise HTTPException(status_code=400, detail=f"Unknown mirror source '{body.source_name}'")
    encrypted = None
    if body.password:
        from services.store_crypto_service import StoreCryptoService
        from services.store_service import _FERNET_KEY_FILE
        encrypted = StoreCryptoService.encrypt_password(body.password, _FERNET_KEY_FILE.read_bytes())
    target_id = repo.upsert_target(
        body.device_id, body.source_name.lower(), body.server_name.strip(),
        body.database_name.strip(), (body.username or "").strip() or None, encrypted,
        body.interval_seconds, (body.tables or "").strip() or None, body.is_enabled,
    )
    return service.public_target(repo.get_target(target_id))


@admin_router.get("/targets/{target_id}/status")
def target_status(target_id: int, _: dict = Depends(require_super_admin)):
    return _call(service.target_status, target_id)


@admin_router.post("/targets/{target_id}/reset")
def reset_target(target_id: int, body: ResetRequest | None = None,
                 _: dict = Depends(require_super_admin)):
    return _call(service.reset, target_id, body.tables if body else None)


@admin_router.delete("/targets/{target_id}")
def delete_target(target_id: int, _: dict = Depends(require_super_admin)):
    repo.delete_target(target_id)
    return {"ok": True}
