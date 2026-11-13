"""Phase 6G found that modules/procurement/reports/reports_router.py's
dashboard/store-analysis/compare endpoints (and their 3 Excel-export
siblings) had zero auth dependency at all -- any logged-in user could pass
any tenant_id and read that tenant's procurement financials. Fixed by
adding the same get_current_user + assert_tenant_access pattern
modules/reports/router.py already uses. This file tests the fix.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from modules.procurement.reports import reports_router as router


SUPERADMIN = {"username": "owner", "tenant_id": None, "is_platform_user": True, "role_names": []}
TENANT_A_USER = {"username": "pm1", "tenant_id": "T1", "is_platform_user": False, "role_names": ["STORE_USER"]}


def test_dashboard_rejects_cross_tenant_access(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        router.dashboard(tenant_id="T2", from_month="2026-01", to_month="2026-06", source="NEXORA", current_user=TENANT_A_USER)
    assert exc.value.status_code == 403


def test_dashboard_allows_own_tenant(monkeypatch):
    monkeypatch.setattr(router.report_service, "dashboard", lambda *a, **k: {"success": True})
    result = router.dashboard(tenant_id="T1", from_month="2026-01", to_month="2026-06", source="NEXORA", current_user=TENANT_A_USER)
    assert result == {"success": True}


def test_dashboard_allows_superadmin_any_tenant(monkeypatch):
    monkeypatch.setattr(router.report_service, "dashboard", lambda *a, **k: {"success": True})
    result = router.dashboard(tenant_id="ANY_TENANT", from_month="2026-01", to_month="2026-06", source="NEXORA", current_user=SUPERADMIN)
    assert result == {"success": True}


def test_store_analysis_rejects_cross_tenant_access():
    with pytest.raises(HTTPException) as exc:
        router.store_analysis(tenant_id="T2", store_id="S1", from_month=None, to_month=None, source="NEXORA", current_user=TENANT_A_USER)
    assert exc.value.status_code == 403


def test_compare_rejects_cross_tenant_access():
    with pytest.raises(HTTPException) as exc:
        router.compare(tenant_id="T2", month_a="2026-01", month_b="2026-02", source="NEXORA", current_user=TENANT_A_USER)
    assert exc.value.status_code == 403


def test_dashboard_excel_rejects_cross_tenant_access():
    with pytest.raises(HTTPException) as exc:
        router.dashboard_excel(tenant_id="T2", from_month="2026-01", to_month="2026-06", source="NEXORA", current_user=TENANT_A_USER)
    assert exc.value.status_code == 403


def test_store_analysis_excel_rejects_cross_tenant_access():
    with pytest.raises(HTTPException) as exc:
        router.store_analysis_excel(tenant_id="T2", store_id="S1", from_month="2026-01", to_month="2026-06", source="NEXORA", current_user=TENANT_A_USER)
    assert exc.value.status_code == 403


def test_compare_excel_rejects_cross_tenant_access():
    with pytest.raises(HTTPException) as exc:
        router.compare_excel(tenant_id="T2", month_a="2026-01", month_b="2026-02", source="NEXORA", current_user=TENANT_A_USER)
    assert exc.value.status_code == 403
