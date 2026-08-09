"""Tenant / store scoping for endpoints that used to trust client-supplied
tenant_id / store_id query params with no server-side check at all.

A logged-in user could previously pass any tenant_id/store_id (Stock
Availability, Reports, Supplier Stock Analysis, /api/stores, /api/tenants...)
and get that tenant/store's data back regardless of their own assignment -
the desktop Supplier Stock client rendered every tenant's stores in one grid
for every role, including purchase and salesman logins.

Only a super admin (or platform user) may see across tenants/stores. Every
other role is locked to their own tenant (JWT claim) and to the stores they
are assigned in dbo.user_store_roles.
"""

from fastapi import HTTPException

from config.database import get_connection
from dependencies.auth import has_full_access


def is_super_admin(user: dict) -> bool:
    if has_full_access(user):
        return True
    names = [str(r or "").strip().lower() for r in (user.get("role_names") or [])]
    return any("superadmin" in name or "super admin" in name for name in names)


def has_unrestricted_scope(user: dict | None) -> bool:
    """Super admins and platform users (no store-scoped role at all) see
    everything. Everyone else - including purchase and salesman roles - is
    locked to their own tenant and assigned stores. `user is None` covers the
    store-agent setup-token flow (no JWT/user at all, see
    dependencies.auth.get_current_user_optional), which is already restricted
    to a fixed whitelist of read-only endpoints by app.py's require_auth
    middleware and stays unrestricted within that whitelist."""
    if user is None:
        return True
    return is_super_admin(user) or bool(user.get("is_platform_user"))


def user_store_ids(user_id) -> list:
    """Stores this user is assigned to, via dbo.user_store_roles."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT DISTINCT CAST(store_id AS VARCHAR(50)) FROM dbo.user_store_roles "
            "WHERE user_id = TRY_CAST(? AS uniqueidentifier) AND is_active = 1",
            (str(user_id),),
        )
        return [row[0] for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def assert_tenant_access(user: dict, tenant_id) -> None:
    """Raise 403 if a non-broad user asks for a tenant that isn't their own."""
    if has_unrestricted_scope(user):
        return
    if str(user.get("tenant_id") or "") != str(tenant_id or ""):
        raise HTTPException(status_code=403, detail="You do not have access to this tenant.")


def assert_store_access(user: dict, tenant_id, store_id) -> None:
    """Raise 403 if a non-broad user asks for a store outside their own tenant
    or outside their assigned stores."""
    assert_tenant_access(user, tenant_id)
    if has_unrestricted_scope(user):
        return
    allowed = user_store_ids(user.get("sub"))
    if str(store_id or "") not in allowed:
        raise HTTPException(status_code=403, detail="You do not have access to this store.")


def scoped_store_ids(user: dict, tenant_id):
    """None = unrestricted (super admin / platform user). Otherwise the list
    of store_ids (possibly empty) this user may see within tenant_id. Also
    enforces tenant access."""
    assert_tenant_access(user, tenant_id)
    if has_unrestricted_scope(user):
        return None
    return user_store_ids(user.get("sub"))
