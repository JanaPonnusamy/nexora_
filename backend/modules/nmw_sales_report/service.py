from fastapi import HTTPException

from dependencies.auth import has_full_access
from dependencies.store_scope import is_salesman_only
from modules.nmw_sales_report import reconcile as _reconcile, repository


def _role_names(user):
    return [str(r or "").strip().lower() for r in (user.get("role_names") or [])]


def _assert_can_view(user):
    """Salesman-only logins may not view NMW dispatch bills at all. Everyone
    else (store admin/manager/purchase manager, super admin) keeps their
    store-scoped or network-wide view from list_bills()."""
    if is_salesman_only(user):
        raise HTTPException(status_code=403, detail="Salesman logins cannot view NMW dispatch bills.")


def is_super_admin(user):
    # SUPER_ADMIN / PLATFORM_OWNER (via has_full_access) plus the display-name
    # 'SuperAdmin' variant that lives in dbo.roles.
    if has_full_access(user):
        return True
    return any("superadmin" in name or "super admin" in name for name in _role_names(user))


def can_view_all(user):
    """Only a genuine super admin / platform user sees every destination store.

    A role NAME containing "purchase"/"manager"/"admin" is NOT itself a signal
    for cross-store access: this deployment has store-scoped roles that share
    the exact same role_name as a would-be network-wide one (e.g. a
    'PURCHASE_MANAGER' bound to only NMA must see only NMA, even though
    another 'PURCHASE_MANAGER' login might be bound elsewhere) - the store
    binding in dbo.user_store_roles is what actually determines scope, not the
    role label. This mirrors dependencies.store_scope.has_unrestricted_scope
    used elsewhere in the platform for the same reason."""
    return is_super_admin(user)


def list_bills(user, tenant_id, store_id, status, date_from, date_to):
    _assert_can_view(user)
    nmw_store_id = repository.get_nmw_store_id(tenant_id)
    if not nmw_store_id:
        return {"bills": [], "can_approve": is_super_admin(user), "scope": "all" if can_view_all(user) else "store"}

    # Throttled, best-effort self-heal: move any superseded (modified-bill) lines
    # out of the live mirror before listing, so doubled bills never surface.
    # Runs in the background and never blocks or fails the report.
    try:
        _reconcile.maybe_auto_reconcile(tenant_id, nmw_store_id)
    except Exception:
        pass

    broad = can_view_all(user)
    if broad:
        # Optional narrowing filter supplied by the client.
        dest_store_ids = [store_id] if store_id else None
        effective_status = status or "all"
    else:
        # Store user: locked to their assigned stores and approved bills only.
        allowed = repository.user_store_ids(user.get("sub"))
        if store_id:
            allowed = [s for s in allowed if s == store_id]
        dest_store_ids = allowed
        effective_status = "approved"

    bills = repository.list_bills(
        tenant_id, nmw_store_id, dest_store_ids, effective_status,
        (date_from or "").strip() or None, (date_to or "").strip() or None,
    )
    return {
        "bills": bills,
        "can_approve": is_super_admin(user),
        "scope": "all" if broad else "store",
    }


def get_bill_items(user, tenant_id, bill_no, bill_date):
    _assert_can_view(user)
    nmw_store_id = repository.get_nmw_store_id(tenant_id)
    if not nmw_store_id:
        return {"items": []}
    items = repository.get_bill_items(tenant_id, nmw_store_id, bill_no, (bill_date or "").strip() or None)
    return {"items": items}


def list_store_cust_codes(user, tenant_id):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can manage store customer codes.")
    return {"stores": repository.list_store_cust_codes(tenant_id)}


def set_store_cust_code(user, tenant_id, store_id, cust_code, code_type="cust"):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can set a store customer code.")
    updated = repository.set_store_cust_code(tenant_id, store_id, cust_code, code_type)
    return {"updated": updated}


def import_cust_codes(user, tenant_id):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can import store customer codes.")
    return repository.import_cust_codes_from_legacy(tenant_id)


def auto_match_cust_codes(user, tenant_id, apply_changes):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can auto-match store customer codes.")
    return repository.auto_match_cust_codes(tenant_id, apply_changes=apply_changes)


def approve(user, req):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can approve NMW dispatch bills.")
    nmw_store_id = repository.get_nmw_store_id(req.tenant_id)
    if not nmw_store_id:
        raise HTTPException(status_code=404, detail="Warehouse store (NMW) not found for this tenant.")
    status = req.status if req.status in ("approved", "pending") else "approved"
    approved_by = user.get("username") or user.get("sub")
    count = repository.approve(req.tenant_id, nmw_store_id, req.bills, status, approved_by, req.remarks)
    return {"approved": count, "status": status}


def reconcile(user, tenant_id, store_id, apply_changes):
    """Move mirror bill-line rows the source POS no longer has (superseded by a
    bill modification) into sync.MProductSaleInformation history. Super admin
    only. store_id defaults to the NMW warehouse."""
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can reconcile NMW bill lines.")
    target_store = (store_id or "").strip() or repository.get_nmw_store_id(tenant_id)
    if not target_store:
        raise HTTPException(status_code=404, detail="No store to reconcile (NMW warehouse not found).")
    try:
        return _reconcile.reconcile_store(tenant_id, target_store, apply_changes=apply_changes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def approve_before(user, tenant_id, cutoff_date):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can bulk-approve NMW bills.")
    nmw_store_id = repository.get_nmw_store_id(tenant_id)
    if not nmw_store_id:
        raise HTTPException(status_code=404, detail="Warehouse store (NMW) not found for this tenant.")
    if not (cutoff_date or "").strip():
        raise HTTPException(status_code=400, detail="A cutoff date (YYYY-MM-DD) is required.")
    approved_by = user.get("username") or user.get("sub")
    count = repository.approve_before(tenant_id, nmw_store_id, cutoff_date.strip(), approved_by)
    return {"approved": count, "cutoff": cutoff_date.strip()}
