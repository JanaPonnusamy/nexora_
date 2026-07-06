"""Procurement Master Integration — pipeline wiring + real-data adaptations
(DB-free): the pipeline orchestrates the real stages; load_source guards on
store; GRN matching falls back to product when the receipt has no supplier.
"""

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from fastapi import HTTPException  # noqa: E402
from modules.procurement import (  # noqa: E402
    pipeline_service, orchestration_service,
    decision_repository, decision_rules,
    reconciliation_rules as recon_rules,
)


def test_pipeline_requires_store():
    with pytest.raises(HTTPException) as ei:
        pipeline_service.run("T1", "", 90, 13, 18, "U1")
    assert ei.value.status_code == 400


def test_pipeline_runs_all_stages(monkeypatch):
    captured = {}

    monkeypatch.setattr(pipeline_service, "_trigger_and_wait_sync",
                        lambda t, s: {"triggered": True, "status": "enqueued", "task_id": "TASK1"})
    monkeypatch.setattr(pipeline_service.src, "product_count", lambda t, s: 1200)
    monkeypatch.setattr(pipeline_service.src, "read_last_grn", lambda t, s: "4567")
    monkeypatch.setattr(pipeline_service.src, "read_last_sale_bill", lambda t, s: "88231")

    def _cycle(payload):
        captured["cycle_payload"] = payload
        return {"cycle_id": "C1"}

    def _refresh(tenant, cycle_id, payload):
        captured["refresh_payload"] = payload
        captured["cycle_id"] = cycle_id
        return {
            "refresh_id": "R1", "generated_product_count": 1200,
            "included_count": 300, "excluded_count": 900, "working_item_count": 300,
        }

    monkeypatch.setattr(orchestration_service, "create_business_cycle", _cycle)
    monkeypatch.setattr(orchestration_service, "create_refresh", _refresh)

    out = pipeline_service.run("T1", "S1", 90, 13, 18, "U1")

    # Real boundaries flow into the cycle + refresh
    assert captured["cycle_payload"]["start_grn_number"] == "4567"
    assert captured["cycle_payload"]["start_sale_bill_number"] == "88231"
    assert captured["refresh_payload"]["rolling_days"] == 90
    assert captured["cycle_id"] == "C1"
    # Summary + timings + honest sync status
    assert out["cycle_id"] == "C1" and out["refresh_id"] == "R1"
    assert out["products_available"] == 1200
    assert out["generated_product_count"] == 1200 and out["working_item_count"] == 300
    assert out["sync"]["status"] == "enqueued"
    assert {"sync_ms", "cycle_ms", "refresh_engine_ms", "total_ms"} <= set(out["timings_ms"])


def test_supplier_queue_ranks_by_product_code(monkeypatch):
    from modules.procurement import supplier_service, supplier_repository, workspace_repository
    monkeypatch.setattr(workspace_repository, "get_item",
                        lambda t, o: {"product_id": "GUID1", "product_code": "12345",
                                      "store_id": "S1"})
    captured = {}
    monkeypatch.setattr(supplier_repository, "top_suppliers",
                        lambda t, code, store, limit: captured.update(
                            {"code": code, "store": store}) or
                            [{"supplier_code": "SUP1", "purchase_frequency": 9}])
    out = supplier_service.get_queue("T1", "OI1", 3)
    # real ranking is keyed by the store ProductCode, not the snapshot GUID
    assert captured["code"] == "12345" and captured["store"] == "S1"
    assert out["suppliers"][0]["supplier_code"] == "SUP1"


def test_load_source_empty_without_store():
    params = decision_rules.DecisionParameters(rolling_days=90, min_days=13, max_days=18)
    assert decision_repository.load_source(None, "T1", None, params) == []


def test_match_receipts_falls_back_to_product_when_no_supplier():
    assignment = {"product_code": "P1", "supplier_code": "SUP1"}
    receipts = [
        {"product_code": "P1", "supplier_code": None, "received_qty": 40, "grn_no": "G1", "supplier_bill_no": None},
        {"product_code": "P2", "supplier_code": None, "received_qty": 99, "grn_no": "G2", "supplier_bill_no": None},
    ]
    total, grn, _ = recon_rules.match_receipts(assignment, receipts)
    assert total == 40 and grn == "G1"   # only P1 matched, by product
