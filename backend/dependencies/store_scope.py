from __future__ import annotations

"""Tenant scoping for endpoints that used to trust client-supplied
tenant_id / store_id query params with no server-side check at all.

A logged-in user could previously pass any tenant_id/store_id and get that
tenant's data back regardless of their own assignment - the desktop
Supplier Stock client rendered every tenant's stores in one grid for every
role, including purchase manager and salesman logins.

The boundary here is the TENANT, not the individual store: Stock
Availability, Reports, and Label Exporter are stock-lookup tools where a
purchase manager or salesman is expected to check any store in their own
tenant (that's the point of the multi-store grid) - they must simply never
see another tenant's data. Screens that DO need a stricter per-store lock
(e.g. NMW Sales Report's dispatch-bill approval queue) implement that
themselves against dbo.user_store_roles rather than through this module -
see modules/nmw_sales_report/repository.py:user_store_ids.

Only a super admin (or platform user, i.e. no tenant_id at all) crosses
tenants, and only with an explicit tenant picker in the UI. Supplier Stock
Analysis additionally blocks purchase manager/salesman entirely regardless
of tenant - see is_supplier_analysis_blocked.
"""

from fastapi import HTTPException

from dependencies.auth import has_full_access


def is_super_admin(user: dict) -> bool:
    if has_full_access(user):
        return True
    names = [str(r or "").strip().lower() for r in (user.get("role_names") or [])]
    return any("superadmin" in name or "super admin" in name for name in names)


def has_unrestricted_scope(user: dict | None) -> bool:
    """Super admins and platform users (no tenant-scoped role at all) see
    every tenant. Everyone else - including purchase manager and salesman
    roles - is locked to their own tenant. `user is None` covers the
    store-agent setup-token flow (no JWT/user at all, see
    dependencies.auth.get_current_user_optional), which is already restricted
    to a fixed whitelist of read-only endpoints by app.py's require_auth
    middleware and stays unrestricted within that whitelist."""
    if user is None:
        return True
    return is_super_admin(user) or bool(user.get("is_platform_user"))


def is_supplier_analysis_blocked(user: dict) -> bool:
    """Supplier Stock Analysis is an admin-only tool: a login whose roles are
    ALL purchase-manager and/or salesman (i.e. no admin-tier role at all) must
    not reach it, regardless of tenant/store. Super admin/platform users are
    never blocked (checked separately by the caller)."""
    names = [str(r or "").strip().lower() for r in (user.get("role_names") or [])]
    if not names:
        return False
    store_level = ("purchase", "salesman", "sales man")
    return all(any(token in name for token in store_level) for name in names)


def assert_tenant_access(user: dict, tenant_id) -> None:
    """Raise 403 if a non-broad user asks for a tenant that isn't their own."""
    if has_unrestricted_scope(user):
        return
    if str(user.get("tenant_id") or "") != str(tenant_id or ""):
        raise HTTPException(status_code=403, detail="You do not have access to this tenant.")


def assert_store_access(user: dict, tenant_id, store_id=None) -> None:
    """Raise 403 if a non-broad user asks for a store outside their own
    tenant. store_id is accepted for call-site symmetry but not itself
    checked - see module docstring for why store-level access isn't
    restricted within a user's own tenant."""
    assert_tenant_access(user, tenant_id)


def assert_label_exporter_store_access(user: dict, tenant_id, store_id) -> None:
    """Label Exporter is a per-store printing workflow (labels physically go
    on that store's shelves), not a lookup tool - so unlike assert_store_access
    it IS store-level, not just tenant-level. Only NMW (the warehouse, which
    prints for every store) and super admin/platform users may pick a store
    other than their own; everyone else is locked to their own store_id, which
    comes from the JWT's primary-role store_id/store_code (see
    controllers.auth_controller.login)."""
    assert_tenant_access(user, tenant_id)
    if has_unrestricted_scope(user):
        return
    if str(user.get("store_code") or "").strip().upper() == "NMW":
        return
    if str(user.get("store_id") or "") == str(store_id or ""):
        return
    raise HTTPException(status_code=403, detail="You do not have access to this store.")
