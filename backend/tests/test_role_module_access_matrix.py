"""Phase 6D: the permission matrix (dbo.role_module_access) already had
assign()/remove() at the repository/service layer (doc 28A S3.1) but no
route ever exposed them, and nothing could set individual action flags
(can_create/can_edit/can_delete/can_export) -- assign() only ever turned on
can_view. This file tests the new GET /matrix and PUT (set_permissions)
routes added to support a real Masters > Permission Management UI.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from controllers import role_module_access_controller as rmac
from dtos.role_module_access_request import RoleModuleAccessRequest


SUPERADMIN = {"username": "owner", "tenant_id": None, "is_platform_user": True, "role_names": []}


def test_get_matrix_returns_service_result(monkeypatch):
    expected = {"roles": [{"role_id": "r1", "role_name": "SUPER_ADMIN"}], "modules": [], "assignments": []}
    monkeypatch.setattr(rmac.RoleModuleAccessService, "get_matrix", lambda self: expected)

    result = rmac.get_matrix(current_user=SUPERADMIN)

    assert result == expected


def test_set_permissions_rejects_unknown_role(monkeypatch):
    monkeypatch.setattr(rmac.RoleModuleAccessService, "role_exists", lambda self, role_id: False)
    body = RoleModuleAccessRequest(role_id="bad-role", module_id="m1", can_view=True)

    with pytest.raises(HTTPException) as exc:
        rmac.set_permissions(body, request=None, current_user=SUPERADMIN)

    assert exc.value.status_code == 404


def test_set_permissions_rejects_unknown_module(monkeypatch):
    monkeypatch.setattr(rmac.RoleModuleAccessService, "role_exists", lambda self, role_id: True)
    monkeypatch.setattr(rmac.RoleModuleAccessService, "module_exists", lambda self, module_id: False)
    body = RoleModuleAccessRequest(role_id="r1", module_id="bad-module", can_view=True)

    with pytest.raises(HTTPException) as exc:
        rmac.set_permissions(body, request=None, current_user=SUPERADMIN)

    assert exc.value.status_code == 404


def test_set_permissions_writes_exact_flags_and_returns_updated_matrix(monkeypatch):
    monkeypatch.setattr(rmac.RoleModuleAccessService, "role_exists", lambda self, role_id: True)
    monkeypatch.setattr(rmac.RoleModuleAccessService, "module_exists", lambda self, module_id: True)
    captured = []
    monkeypatch.setattr(
        rmac.RoleModuleAccessService, "set_permissions",
        lambda self, role_id, module_id, can_view, can_create, can_edit, can_delete, can_export:
            captured.append((role_id, module_id, can_view, can_create, can_edit, can_delete, can_export)),
    )
    updated_matrix = {"role_id": "r1", "role_name": "STORE_ADMIN", "total_modules": 1, "modules": []}
    monkeypatch.setattr(rmac.RoleModuleAccessService, "get_role_permission_matrix", lambda self, role_id: updated_matrix)

    body = RoleModuleAccessRequest(
        role_id="r1", module_id="m1",
        can_view=True, can_create=True, can_edit=False, can_delete=False, can_export=True,
    )
    result = rmac.set_permissions(body, request=None, current_user=SUPERADMIN)

    assert captured == [("r1", "m1", True, True, False, False, True)]
    assert result == updated_matrix


def test_set_permissions_can_turn_everything_off():
    """A role being fully de-permissioned from a module (all flags False,
    e.g. revoking access entirely while keeping the row for history) must
    be a valid request, not silently rejected or treated as a no-op."""
    body = RoleModuleAccessRequest(role_id="r1", module_id="m1")
    assert body.can_view is False
    assert body.can_create is False
    assert body.can_edit is False
    assert body.can_delete is False
    assert body.can_export is False
