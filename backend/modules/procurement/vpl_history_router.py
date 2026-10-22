"""Read, edit, refresh, and inspect VPL history.

Process memory only. Migration 0027 is not applied. These routes do not
call decision_rules.evaluate or replace an existing refresh in the database.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from dependencies.store_scope import assert_tenant_access
from modules.procurement.access import require_procurement_admin
from modules.procurement.vpl_history import WORKSPACE, VplConflict, VplError

router = APIRouter(prefix="/vpl-history", tags=["VPL History"])


class EditBody(BaseModel):
    product_code: str
    expected_version: int
    editor_id: str
    changes: dict


class RefreshBody(BaseModel):
    editor_id: str
    rule_snapshot_id: Optional[str] = None
    lines: list


class OpenBody(BaseModel):
    editor_id: str
    rule_snapshot_id: Optional[str] = None
    lines: list


class ProductActionBody(BaseModel):
    product_code: str
    editor_id: str


def _fail(exc: VplError):
    status = 409 if isinstance(exc, VplConflict) else 422
    raise HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


@router.get("/working")
def get_working(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    cycle_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    try:
        body = WORKSPACE.working(tenant_id, store_id, cycle_id)
    except VplError as exc:
        _fail(exc)
    body["persistence"] = "memory_until_migration_0027"
    body["live_engine_unchanged"] = True
    return body


@router.post("/working")
def open_working(
    payload: OpenBody,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    cycle_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    try:
        return WORKSPACE.open_cycle(tenant_id, store_id, cycle_id, payload.lines, payload.rule_snapshot_id)
    except VplError as exc:
        _fail(exc)


@router.put("/working/lines")
def edit_line(
    payload: EditBody,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    cycle_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    try:
        return WORKSPACE.edit(
            tenant_id, store_id, cycle_id, payload.product_code, payload.changes, payload.expected_version, payload.editor_id
        )
    except VplError as exc:
        _fail(exc)


@router.post("/refresh")
def refresh(
    payload: RefreshBody,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    cycle_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    try:
        body = WORKSPACE.refresh(
            tenant_id, store_id, cycle_id, payload.lines, payload.rule_snapshot_id, payload.editor_id
        )
    except VplError as exc:
        _fail(exc)
    body["live_engine_unchanged"] = True
    body["note"] = (
        "Previous active lines were copied into history. "
        "Touched lines missing from this generation are in removed_manual_review and are not orderable. "
        "Confirmed orders were not recalculated. Live generation was not called."
    )
    return body


def _run_guard(method, payload, tenant_id, store_id, cycle_id, current_user):
    assert_tenant_access(current_user, tenant_id)
    try:
        return method(tenant_id, store_id, cycle_id, payload.product_code)
    except VplError as exc:
        _fail(exc)


@router.post("/working/assign")
def assign_supplier(
    payload: ProductActionBody,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    cycle_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    return _run_guard(WORKSPACE.assign_supplier, payload, tenant_id, store_id, cycle_id, current_user)


@router.post("/working/export")
def export_lines(
    payload: ProductActionBody,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    cycle_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    return _run_guard(WORKSPACE.export_lines, payload, tenant_id, store_id, cycle_id, current_user)


@router.post("/working/order")
def place_order(
    payload: ProductActionBody,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    cycle_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    return _run_guard(WORKSPACE.place_order, payload, tenant_id, store_id, cycle_id, current_user)


@router.post("/working/portal")
def submit_to_portal(
    payload: ProductActionBody,
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    cycle_id: str = Query(...),
    current_user: dict = Depends(require_procurement_admin),
):
    return _run_guard(WORKSPACE.submit_to_portal, payload, tenant_id, store_id, cycle_id, current_user)


@router.get("/history")
def history(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
    current_user: dict = Depends(require_procurement_admin),
):
    assert_tenant_access(current_user, tenant_id)
    return WORKSPACE.history_headers(tenant_id, store_id, limit)


@router.get("/history/{history_id}")
def history_detail(history_id: str, current_user: dict = Depends(require_procurement_admin)):
    del current_user
    try:
        return WORKSPACE.history_detail(history_id)
    except VplError as exc:
        _fail(exc)
