"""HTTP API for the Procurement Rules Registry.

Overrides stay in the process registry until migration 0026 is approved
and applied. These routes do not call the decision engine.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dependencies.auth import has_full_access
from dependencies.store_scope import assert_tenant_access
from modules.procurement.access import require_procurement_admin
from modules.procurement.rules_resolution import REGISTRY, RuleConflict, RuleRejected

router = APIRouter(prefix="/rules", tags=["Procurement Rules"])


class RuleWrite(BaseModel):
    value: object
    editor_id: str
    reason: str
    expected_version: Optional[int] = None


def _reject(exc: RuleRejected):
    status = 409 if isinstance(exc, RuleConflict) else 422
    raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


@router.get("/catalog")
def catalog(current_user: dict = Depends(require_procurement_admin)):
    del current_user
    return {
        "persistence": "memory_until_migration_0026",
        "live_engine_unchanged": True,
        "rules": REGISTRY.catalog(),
    }


@router.get("/effective")
def effective(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    return REGISTRY.resolve(tenant_id, store_id)


@router.get("/history")
def history(
    tenant_id: Optional[str] = Query(None),
    store_id: Optional[str] = Query(None),
    rule_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_procurement_admin),
):
    if not tenant_id:
        if not has_full_access(current_user):
            raise HTTPException(status_code=422, detail={"code": "TENANT", "message": "tenant_id is required."})
    else:
        assert_tenant_access(current_user, tenant_id)
    return {"changes": REGISTRY.history(tenant_id, store_id, rule_id)}


@router.put("/defaults/{rule_id}")
def put_default(rule_id: str, payload: RuleWrite, current_user: dict = Depends(require_procurement_admin)):
    del current_user
    if payload.expected_version is None:
        raise HTTPException(status_code=422, detail={"code": "VERSION", "message": "expected_version is required."})
    try:
        saved = REGISTRY.set_default(rule_id, payload.value, payload.editor_id, payload.reason, payload.expected_version)
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "ABSENT", "message": "Unknown rule."})
    except RuleRejected as exc:
        _reject(exc)
    return {
        "saved": saved,
        "affects_future_calculations_only": True,
        "live_engine_unchanged": True,
    }


@router.put("/overrides/{rule_id}")
def put_override(
    rule_id: str,
    payload: RuleWrite,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    try:
        saved = REGISTRY.set_override(
            tenant_id,
            store_id,
            rule_id,
            payload.value,
            payload.editor_id,
            payload.reason,
            payload.expected_version,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "ABSENT", "message": "Unknown rule."})
    except RuleRejected as exc:
        _reject(exc)
    return {
        "saved": saved,
        "affects_future_calculations_only": True,
        "live_engine_unchanged": True,
    }


@router.post("/overrides/{rule_id}/reset")
def reset_override(
    rule_id: str,
    payload: RuleWrite,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    if payload.expected_version is None:
        raise HTTPException(status_code=422, detail={"code": "VERSION", "message": "expected_version is required."})
    try:
        REGISTRY.reset_override(
            tenant_id, store_id, rule_id, payload.editor_id, payload.reason, payload.expected_version
        )
    except KeyError:
        raise HTTPException(status_code=404, detail={"code": "ABSENT", "message": "Unknown rule."})
    except RuleRejected as exc:
        _reject(exc)
    return REGISTRY.resolve(tenant_id, store_id)


@router.post("/snapshots")
def create_snapshot(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    editor_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    body = REGISTRY.take_snapshot(tenant_id, store_id, editor_id)
    body["attached_to_refresh"] = False
    body["note"] = "Snapshot is stored for a future refresh. Existing refreshes are not rewritten."
    return body
