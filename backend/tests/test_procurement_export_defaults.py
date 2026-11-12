"""Tenant-wide desktop export-defaults lock (pm_router.py GET/PUT
/export-defaults): a superadmin may lock the Procurement/Order Workspace
export file-format + columns for a tenant; every other role can only read
the locked value. See docs/NEXORA_MEDIQ_AUDIT/12_UNCOMMITTED_WORK_VALIDATION.md
and 13_TENANT_EXPORT_FEATURE_TEST_REPORT.md -- this feature had zero tests
before Phase 3 of the NEXORA MEDIQ audit."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from modules.procurement import pm_router as router
from modules.procurement.pm_schemas import TenantExportDefaultsUpdate

SUPERADMIN = {"username": "owner", "tenant_id": "T1", "is_platform_user": True, "role_names": []}
REGULAR_USER = {"username": "pm1", "tenant_id": "T1", "is_platform_user": False, "role_names": ["PM"]}


def test_get_export_defaults_with_no_row_returns_unlocked(monkeypatch):
    monkeypatch.setattr(router, "assert_tenant_access", lambda user, tenant_id: None)
    monkeypatch.setattr(router.tenant_export_defaults_repository, "get", lambda tenant_id: None)

    out = router.tenant_export_defaults(tenant_id="T1", current_user=REGULAR_USER)

    assert out == {"file_format": None, "columns": None, "locked": False}


def test_get_export_defaults_with_row_returns_locked_values(monkeypatch):
    monkeypatch.setattr(router, "assert_tenant_access", lambda user, tenant_id: None)
    monkeypatch.setattr(
        router.tenant_export_defaults_repository, "get",
        lambda tenant_id: {"file_format": "xlsx", "columns": "mrp,rack,category"},
    )

    out = router.tenant_export_defaults(tenant_id="T1", current_user=REGULAR_USER)

    assert out == {"file_format": "xlsx", "columns": ["mrp", "rack", "category"], "locked": True}


def test_put_export_defaults_rejected_for_non_superadmin(monkeypatch):
    monkeypatch.setattr(router, "assert_tenant_access", lambda user, tenant_id: None)
    monkeypatch.setattr(router, "has_full_access", lambda user: False)
    calls = []
    monkeypatch.setattr(
        router.tenant_export_defaults_repository, "upsert",
        lambda *a, **k: calls.append((a, k)),
    )
    body = TenantExportDefaultsUpdate(file_format="xls", columns=["mrp"])

    with pytest.raises(HTTPException) as exc_info:
        router.update_tenant_export_defaults(body, tenant_id="T1", current_user=REGULAR_USER)

    assert exc_info.value.status_code == 403
    assert not calls  # the repository must never be touched on a rejected write


def test_put_export_defaults_succeeds_for_superadmin(monkeypatch):
    monkeypatch.setattr(router, "assert_tenant_access", lambda user, tenant_id: None)
    monkeypatch.setattr(router, "has_full_access", lambda user: True)
    calls = []
    monkeypatch.setattr(
        router.tenant_export_defaults_repository, "upsert",
        lambda *a, **k: calls.append((a, k)),
    )
    body = TenantExportDefaultsUpdate(file_format="xlsx", columns=["mrp", "rack"])

    out = router.update_tenant_export_defaults(body, tenant_id="T1", current_user=SUPERADMIN)

    assert out == {"ok": True}
    assert calls == [(("T1", "xlsx", "mrp,rack", "owner"), {})]


def test_put_export_defaults_rejects_unauthorized_tenant(monkeypatch):
    def deny(user, tenant_id):
        raise HTTPException(status_code=403, detail="tenant mismatch")

    monkeypatch.setattr(router, "assert_tenant_access", deny)
    body = TenantExportDefaultsUpdate(file_format="xls", columns=[])

    with pytest.raises(HTTPException) as exc_info:
        router.update_tenant_export_defaults(body, tenant_id="OTHER-TENANT", current_user=SUPERADMIN)

    assert exc_info.value.status_code == 403


def test_file_format_is_whitelisted_by_schema():
    with pytest.raises(ValidationError):
        TenantExportDefaultsUpdate(file_format="docx", columns=[])


def test_file_format_defaults_to_xls_when_omitted():
    assert TenantExportDefaultsUpdate(columns=["mrp"]).file_format == "xls"


def test_columns_are_whitelisted_against_known_export_keys():
    with pytest.raises(ValidationError):
        TenantExportDefaultsUpdate(file_format="xls", columns=["mrp", "notARealColumn"])


def test_known_column_keys_are_accepted():
    update = TenantExportDefaultsUpdate(file_format="xls", columns=["mrp", "rack", "category"])
    assert update.columns == ["mrp", "rack", "category"]
