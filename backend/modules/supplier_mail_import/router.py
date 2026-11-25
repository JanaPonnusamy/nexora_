"""Supplier mail import API: tenant mailbox, per-supplier switch, log, run now.
Same access tier as Supplier Stock Analysis (its Excel import is what this
automates)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dependencies.store_scope import assert_store_access, assert_tenant_access
from modules.supplier_mail_import import repository, service
from modules.supplier_stock_analysis.repository import _store_code
from modules.supplier_stock_analysis.router import require_admin_role

router = APIRouter(prefix="/api/supplier-mail-import", tags=["Supplier Mail Import"])


class MailConfigPayload(BaseModel):
    enabled: bool = False
    imap_host: str = ""
    imap_port: int = 993
    use_ssl: bool = True
    username: str = ""
    password: Optional[str] = None  # blank keeps the saved password
    folder: str = "INBOX"
    poll_minutes: int = 15
    lookback_days: int = 2


class SupplierMailPayload(BaseModel):
    tenant_id: str
    store_id: str
    supplier_code: str
    enabled: bool
    mail_from: str = ""
    subject_filter: str = ""


def _actor(user):
    return user.get("username") or user.get("sub")


def _store(user, tenant_id, store_id):
    assert_store_access(user, tenant_id, store_id)
    code = _store_code(tenant_id, store_id)
    if not code:
        raise HTTPException(status_code=404, detail="Store not found.")
    return code


@router.get("/config")
def read_config(tenant_id: str, current_user: dict = Depends(require_admin_role)):
    assert_tenant_access(current_user, tenant_id)
    return service.get_config(tenant_id)


@router.put("/config")
def write_config(tenant_id: str, payload: MailConfigPayload, current_user: dict = Depends(require_admin_role)):
    assert_tenant_access(current_user, tenant_id)
    try:
        return service.save_config(tenant_id, payload.dict(), _actor(current_user))
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@router.post("/config/test")
def test_config(tenant_id: str, payload: Optional[MailConfigPayload] = None, current_user: dict = Depends(require_admin_role)):
    assert_tenant_access(current_user, tenant_id)
    try:
        return service.test_connection(tenant_id, payload.dict() if payload else None)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))


@router.get("/suppliers")
def suppliers(tenant_id: str, store_id: str, current_user: dict = Depends(require_admin_role)):
    store_code = _store(current_user, tenant_id, store_id)
    return {"suppliers": service.list_suppliers(tenant_id, store_id, store_code)}


@router.put("/suppliers")
def save_supplier(payload: SupplierMailPayload, current_user: dict = Depends(require_admin_role)):
    _store(current_user, payload.tenant_id, payload.store_id)
    try:
        service.save_supplier(
            payload.tenant_id, payload.store_id, payload.supplier_code, payload.enabled,
            payload.mail_from, payload.subject_filter, _actor(current_user),
        )
    except LookupError as ex:
        raise HTTPException(status_code=404, detail=str(ex))
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex))
    return {"success": True}


@router.post("/run")
def run_now(tenant_id: str, wait: bool = True, current_user: dict = Depends(require_admin_role)):
    """Check the mailbox now. wait=false returns immediately (result lands in
    the log / config last_poll_*)."""
    assert_tenant_access(current_user, tenant_id)
    if not wait:
        service.run_tenant_in_background(tenant_id)
        return {"ok": True, "message": "Mail check started."}
    return service.run_tenant(tenant_id)


@router.get("/log")
def log(
    tenant_id: str,
    store_id: Optional[str] = None,
    supplier_code: Optional[str] = None,
    limit: int = 100,
    current_user: dict = Depends(require_admin_role),
):
    store_code = _store(current_user, tenant_id, store_id) if store_id else None
    if not store_id:
        assert_tenant_access(current_user, tenant_id)
    return {"rows": repository.list_log(tenant_id, store_code, supplier_code, min(max(limit, 1), 500))}
