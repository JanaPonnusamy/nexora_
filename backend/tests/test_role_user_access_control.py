"""Phase 6A found that role_controller.py, user_controller.py,
role_module_access_controller.py, and user_role_controller.py's mutation
(and most read) endpoints had zero permission gating beyond "is this a
valid JWT at all" -- any authenticated Salesman/Stock-Viewer login could
create roles, edit permissions, or deactivate the only remaining
superadmin. See docs/NEXORA_MEDIQ_AUDIT/28A_PHASE6A_ARCHITECTURE_BASELINE.md
S3.4. This file tests the fix: require_super_admin gating on admin-only
routes, tenant-scoping on user listing/detail, and last-active-superadmin
protection on both role deactivation and user deactivation.

FastAPI route functions are called directly (not through the app/TestClient),
following the established pattern in test_procurement_export_defaults.py --
dependencies are exercised explicitly where the test is about the gate
itself, and bypassed via monkeypatch where the test is about what the route
body does once past the gate.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from dependencies.store_scope import require_super_admin, has_unrestricted_scope
from controllers import role_controller, user_controller, user_role_controller
from controllers import role_module_access_controller
from dtos.role_request import RoleRequest, RoleStatusRequest
from dtos.user_request import UserRequest, UserStatusRequest


SUPERADMIN = {"username": "owner", "sub": "u-admin", "tenant_id": None, "is_platform_user": True, "role_names": []}
PLATFORM_OWNER = {"username": "po", "sub": "u-po", "tenant_id": None, "is_platform_user": False, "role_names": ["PLATFORM_OWNER"]}
STORE_USER = {"username": "clerk", "sub": "u-clerk", "tenant_id": "T1", "is_platform_user": False, "role_names": ["STORE_USER"]}
SALESMAN = {"username": "sales1", "sub": "u-sales", "tenant_id": "T1", "is_platform_user": False, "role_names": ["SALESMAN"]}


# ---------------------------------------------------------------------------
# require_super_admin gate itself
# ---------------------------------------------------------------------------

def test_require_super_admin_rejects_store_level_user():
    with pytest.raises(HTTPException) as exc:
        require_super_admin(STORE_USER)
    assert exc.value.status_code == 403


def test_require_super_admin_rejects_salesman():
    with pytest.raises(HTTPException) as exc:
        require_super_admin(SALESMAN)
    assert exc.value.status_code == 403


def test_require_super_admin_accepts_platform_user():
    assert require_super_admin(SUPERADMIN) == SUPERADMIN


def test_require_super_admin_accepts_platform_owner_role_name():
    assert require_super_admin(PLATFORM_OWNER) == PLATFORM_OWNER


# ---------------------------------------------------------------------------
# role_controller: every mutation + the two GET routes must be behind
# require_super_admin (verified by reading the route's own Depends default,
# since Depends() markers are inert outside a real FastAPI call -- the
# meaningful assertion is that calling require_super_admin with a
# non-admin user raises, which is already proven above; here we additionally
# confirm each route signature actually wires the dependency).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("route,param_name", [
    (role_controller.seed_roles, "current_user"),
    (role_controller.get_roles, "current_user"),
    (role_controller.get_role, "current_user"),
    (role_controller.create_role, "current_user"),
    (role_controller.update_role, "current_user"),
    (role_controller.set_role_status, "current_user"),
])
def test_role_controller_routes_depend_on_require_super_admin(route, param_name):
    import inspect
    sig = inspect.signature(route)
    default = sig.parameters[param_name].default
    assert default.dependency is require_super_admin


@pytest.mark.parametrize("route,param_name", [
    (role_module_access_controller.seed_permissions, "current_user"),
    (role_module_access_controller.get_role_permissions, "current_user"),
])
def test_role_module_access_routes_depend_on_require_super_admin(route, param_name):
    import inspect
    sig = inspect.signature(route)
    default = sig.parameters[param_name].default
    assert default.dependency is require_super_admin


@pytest.mark.parametrize("route,param_name", [
    (user_controller.create_user, "current_user"),
    (user_controller.update_user, "current_user"),
    (user_controller.set_user_status, "current_user"),
    (user_controller.get_users_by_store, "current_user"),
])
def test_user_controller_mutations_depend_on_require_super_admin(route, param_name):
    import inspect
    sig = inspect.signature(route)
    default = sig.parameters[param_name].default
    assert default.dependency is require_super_admin


@pytest.mark.parametrize("route,param_name", [
    (user_role_controller.seed, "current_user"),
    (user_role_controller.seed_defaults, "current_user"),
    (user_role_controller.seed_role_users, "current_user"),
])
def test_user_role_seed_routes_depend_on_require_super_admin(route, param_name):
    import inspect
    sig = inspect.signature(route)
    default = sig.parameters[param_name].default
    assert default.dependency is require_super_admin


# ---------------------------------------------------------------------------
# GET /api/users and GET /api/users/{id}: tenant-scoped for non-admins
# ---------------------------------------------------------------------------

def test_get_users_forces_callers_own_tenant_when_not_unrestricted(monkeypatch):
    captured = {}

    def fake_get_all(search, tenant_id, store_id, role_id, status):
        captured["tenant_id"] = tenant_id
        return []

    monkeypatch.setattr(user_controller.UserService, "get_all", lambda self, *a, **k: fake_get_all(*a, **k))

    user_controller.get_users(search=None, tenant_id="SOMEONE_ELSE_TENANT", store_id=None, role_id=None, status=None, current_user=STORE_USER)

    assert captured["tenant_id"] == "T1"  # STORE_USER's own tenant, not the requested one


def test_get_users_lets_superadmin_pass_any_tenant(monkeypatch):
    captured = {}

    def fake_get_all(search, tenant_id, store_id, role_id, status):
        captured["tenant_id"] = tenant_id
        return []

    monkeypatch.setattr(user_controller.UserService, "get_all", lambda self, *a, **k: fake_get_all(*a, **k))

    user_controller.get_users(search=None, tenant_id="ANY_TENANT", store_id=None, role_id=None, status=None, current_user=SUPERADMIN)

    assert captured["tenant_id"] == "ANY_TENANT"


def test_get_user_detail_rejects_cross_tenant_access(monkeypatch):
    other_tenant_row = (
        "u-other", "bob", "Bob Jones", "Bob", "Jones", "bob@x.com", "555",
        "T2", "Tenant Two", False, True, None, 0, 1,
    )
    monkeypatch.setattr(user_controller.UserService, "get_by_id", lambda self, user_id: other_tenant_row)

    with pytest.raises(HTTPException) as exc:
        user_controller.get_user(user_id="u-other", current_user=STORE_USER)

    assert exc.value.status_code == 403


def test_get_user_detail_allows_superadmin_cross_tenant():
    other_tenant_row = (
        "u-other", "bob", "Bob Jones", "Bob", "Jones", "bob@x.com", "555",
        "T2", "Tenant Two", False, True, None, 0, 1,
    )
    import controllers.user_controller as uc
    orig = uc.UserService.get_by_id
    uc.UserService.get_by_id = lambda self, user_id: other_tenant_row
    try:
        result = uc.get_user(user_id="u-other", current_user=SUPERADMIN)
        assert result["user_id"] == "u-other"
    finally:
        uc.UserService.get_by_id = orig


# ---------------------------------------------------------------------------
# Last-active-superadmin protection
# ---------------------------------------------------------------------------

def test_set_role_status_blocks_deactivating_last_superadmin_role(monkeypatch):
    monkeypatch.setattr(role_controller.RoleService, "get_by_id", lambda self, role_id: {"role_id": role_id, "role_name": "SUPER_ADMIN", "description": None, "is_active": True, "assigned_users": 1})
    monkeypatch.setattr(role_controller.RoleService, "is_superadmin_tier_role", lambda self, role_id: True)
    monkeypatch.setattr(role_controller.RoleService, "remaining_superadmins_if_role_deactivated", lambda self, role_id: 0)
    set_active_calls = []
    monkeypatch.setattr(role_controller.RoleService, "set_active", lambda self, role_id, is_active: set_active_calls.append((role_id, is_active)))

    with pytest.raises(HTTPException) as exc:
        role_controller.set_role_status(
            role_id="r-super", body=RoleStatusRequest(is_active=False),
            request=None, current_user=SUPERADMIN,
        )

    assert exc.value.status_code == 409
    assert not set_active_calls  # must never touch the DB on a rejected deactivation


def test_set_role_status_allows_deactivating_superadmin_role_when_others_remain(monkeypatch):
    monkeypatch.setattr(role_controller.RoleService, "get_by_id", lambda self, role_id: {"role_id": role_id, "role_name": "SUPER_ADMIN", "description": None, "is_active": True, "assigned_users": 2})
    monkeypatch.setattr(role_controller.RoleService, "is_superadmin_tier_role", lambda self, role_id: True)
    monkeypatch.setattr(role_controller.RoleService, "remaining_superadmins_if_role_deactivated", lambda self, role_id: 1)
    set_active_calls = []
    monkeypatch.setattr(role_controller.RoleService, "set_active", lambda self, role_id, is_active: set_active_calls.append((role_id, is_active)))

    role_controller.set_role_status(
        role_id="r-super", body=RoleStatusRequest(is_active=False),
        request=None, current_user=SUPERADMIN,
    )

    assert set_active_calls == [("r-super", False)]


def test_set_role_status_never_blocks_activating_a_role(monkeypatch):
    """The last-superadmin check only applies when deactivating -- activating
    a role (or any non-superadmin role's deactivation) must never be blocked
    by this guard."""
    monkeypatch.setattr(role_controller.RoleService, "get_by_id", lambda self, role_id: {"role_id": role_id, "role_name": "STORE_USER", "description": None, "is_active": False, "assigned_users": 0})
    monkeypatch.setattr(role_controller.RoleService, "is_superadmin_tier_role", lambda self, role_id: False)
    set_active_calls = []
    monkeypatch.setattr(role_controller.RoleService, "set_active", lambda self, role_id, is_active: set_active_calls.append((role_id, is_active)))

    role_controller.set_role_status(
        role_id="r-store", body=RoleStatusRequest(is_active=True),
        request=None, current_user=SUPERADMIN,
    )

    assert set_active_calls == [("r-store", True)]


def test_set_user_status_blocks_deactivating_last_superadmin_user(monkeypatch):
    user_row = ("u-admin", "owner", "Owner Account", "Owner", "Account", None, None, None, None, True, True, None, 0, 1)
    monkeypatch.setattr(user_controller.UserService, "get_by_id", lambda self, user_id: user_row)
    monkeypatch.setattr(user_controller.RoleService, "remaining_superadmins_if_user_deactivated", lambda self, user_id: 0)
    set_active_calls = []
    monkeypatch.setattr(user_controller.UserService, "set_active", lambda self, user_id, is_active: set_active_calls.append((user_id, is_active)))

    with pytest.raises(HTTPException) as exc:
        user_controller.set_user_status(
            user_id="u-admin", body=UserStatusRequest(is_active=False),
            request=None, current_user=SUPERADMIN,
        )

    assert exc.value.status_code == 409
    assert not set_active_calls


def test_set_user_status_allows_deactivating_non_last_superadmin(monkeypatch):
    user_row = ("u-admin2", "owner2", "Owner Two", "Owner", "Two", None, None, None, None, True, True, None, 0, 1)
    monkeypatch.setattr(user_controller.UserService, "get_by_id", lambda self, user_id: user_row)
    monkeypatch.setattr(user_controller.RoleService, "remaining_superadmins_if_user_deactivated", lambda self, user_id: 1)
    set_active_calls = []
    monkeypatch.setattr(user_controller.UserService, "set_active", lambda self, user_id, is_active: set_active_calls.append((user_id, is_active)))

    user_controller.set_user_status(
        user_id="u-admin2", body=UserStatusRequest(is_active=False),
        request=None, current_user=SUPERADMIN,
    )

    assert set_active_calls == [("u-admin2", False)]


def test_set_user_status_never_checks_superadmin_count_when_activating(monkeypatch):
    user_row = ("u-clerk", "clerk", "Store Clerk", "Store", "Clerk", None, None, "T1", "Tenant One", False, False, None, 0, 1)
    monkeypatch.setattr(user_controller.UserService, "get_by_id", lambda self, user_id: user_row)
    called = []
    monkeypatch.setattr(user_controller.RoleService, "remaining_superadmins_if_user_deactivated", lambda self, user_id: called.append(user_id) or 0)
    set_active_calls = []
    monkeypatch.setattr(user_controller.UserService, "set_active", lambda self, user_id, is_active: set_active_calls.append((user_id, is_active)))

    user_controller.set_user_status(
        user_id="u-clerk", body=UserStatusRequest(is_active=True),
        request=None, current_user=SUPERADMIN,
    )

    assert not called  # activating never needs the superadmin-count check
    assert set_active_calls == [("u-clerk", True)]


# ---------------------------------------------------------------------------
# user_role_controller: a non-admin may only read their own role assignment
# ---------------------------------------------------------------------------

def test_get_user_roles_rejects_reading_another_users_roles(monkeypatch):
    monkeypatch.setattr(user_role_controller.UserRoleService, "get_roles", lambda self, user_id: [])

    with pytest.raises(HTTPException) as exc:
        user_role_controller.get_user_roles(user_id="u-someone-else", current_user=STORE_USER)

    assert exc.value.status_code == 403


def test_get_user_roles_allows_reading_own_roles(monkeypatch):
    monkeypatch.setattr(user_role_controller.UserRoleService, "get_roles", lambda self, user_id: [{"role_name": "STORE_USER"}])

    result = user_role_controller.get_user_roles(user_id="u-clerk", current_user=STORE_USER)

    assert result == [{"role_name": "STORE_USER"}]


def test_get_user_roles_allows_superadmin_to_read_anyone(monkeypatch):
    monkeypatch.setattr(user_role_controller.UserRoleService, "get_roles", lambda self, user_id: [{"role_name": "STORE_USER"}])

    result = user_role_controller.get_user_roles(user_id="u-someone-else", current_user=SUPERADMIN)

    assert result == [{"role_name": "STORE_USER"}]
