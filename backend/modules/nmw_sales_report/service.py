from fastapi import HTTPException

from dependencies.auth import has_full_access
from modules.nmw_sales_report import repository


def _role_names(user):
    return [str(r or "").strip().lower() for r in (user.get("role_names") or [])]


def is_super_admin(user):
    # SUPER_ADMIN / PLATFORM_OWNER (via has_full_access) plus the display-name
    # 'SuperAdmin' variant that lives in dbo.roles.
    if has_full_access(user):
        return True
    return any("superadmin" in name or "super admin" in name for name in _role_names(user))


def can_view_all(user):
    """Broad viewers see every destination store and pending bills: super admins,
    admin/manager roles, and purchase-manager users."""
    if is_super_admin(user):
        return True
    broad = ("admin", "manager", "purchase", "owner")
    return any(any(token in name for token in broad) for name in _role_names(user))


def list_bills(user, tenant_id, store_id, status, date_from, date_to):
    nmw_store_id = repository.get_nmw_store_id(tenant_id)
    if not nmw_store_id:
        return {"bills": [], "can_approve": is_super_admin(user), "scope": "all" if can_view_all(user) else "store"}

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
    nmw_store_id = repository.get_nmw_store_id(tenant_id)
    if not nmw_store_id:
        return {"items": []}
    items = repository.get_bill_items(tenant_id, nmw_store_id, bill_no, (bill_date or "").strip() or None)
    return {"items": items}


def list_store_cust_codes(user, tenant_id):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can manage store customer codes.")
    return {"stores": repository.list_store_cust_codes(tenant_id)}


def set_store_cust_code(user, tenant_id, store_id, cust_code):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can set a store customer code.")
    updated = repository.set_store_cust_code(tenant_id, store_id, cust_code)
    return {"updated": updated}


def import_cust_codes(user, tenant_id):
    if not is_super_admin(user):
        raise HTTPException(status_code=403, detail="Only a super admin can import store customer codes.")
    return repository.import_cust_codes_from_legacy(tenant_id)


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
