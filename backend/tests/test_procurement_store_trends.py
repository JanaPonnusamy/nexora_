"""Procurement "All Stores" panel -- suggestion_service.store_trends: this
store first, then every mapped store by code, each with the same latest 4
months (gaps as None), unmapped stores left out."""
from __future__ import annotations

from modules.procurement import suggestion_service as svc

STORES = [
    {"store_id": "S-NMA", "store_code": "NMA", "store_name": "Nathan A"},
    {"store_id": "S-NMC", "store_code": "NMC", "store_name": "Nathan C"},
    {"store_id": "S-NMW", "store_code": "NMW", "store_name": "Warehouse"},
    {"store_id": "S-NMX", "store_code": "NMX", "store_name": "Unmapped"},
]


def test_store_trends_orders_stores_and_fills_months(monkeypatch):
    span = svc._last_months(svc.TREND_MONTHS + 1)
    months = span[1:]  # the current month has a row (NMC below)
    assert len(months) == 4 and months == sorted(months)
    monkeypatch.setattr(svc.intel_repo, "list_active_stores", lambda tenant: STORES)
    monkeypatch.setattr(svc.intel_repo, "resolve_mapped_stores", lambda tenant, sid, code, others: {
        "S-NMC": {"product_code": "77", "product_name": "D-PROTIN C"},
        "S-NMA": {"product_code": "5433", "product_name": "D-PROTIN A"},
    })
    seen = {}

    def movement(tenant, pairs, n):
        seen["pairs"], seen["n"] = pairs, n
        return [
            {"store_id": "s-nmw", "ym": months[0], "qty_in": 5, "qty_out": 6, "stock": 3},
            {"store_id": "S-NMC", "ym": months[3], "qty_in": 1, "qty_out": 0, "stock": 3},
        ]

    monkeypatch.setattr(svc.repo, "store_monthly_movement", movement)
    out = svc.store_trends("T", "S-NMW", " 5433 ")

    assert seen["n"] == 5 and seen["pairs"][0] == ("S-NMW", "5433")
    assert out["months"] == months
    assert all([m["ym"] for m in s["months"]] == months for s in out["stores"])
    assert [s["store_code"] for s in out["stores"]] == ["NMW", "NMA", "NMC"]
    nmw, nma, nmc = out["stores"]
    assert nmw["current"] and not nma["current"]
    assert nmw["months"][0] == {"ym": months[0], "in": 5.0, "out": 6.0, "stock": 3.0}
    assert nmw["months"][1]["out"] is None  # month with no ProductTrans row
    assert all(m["stock"] is None for m in nma["months"])
    assert nmc["product_code"] == "77" and nmc["months"][3]["stock"] == 3.0
    assert nmc["months"][3]["out"] == 0.0  # a real zero stays 0, not None


def test_store_trends_ends_at_previous_month_when_current_has_no_rows(monkeypatch):
    span = svc._last_months(svc.TREND_MONTHS + 1)
    monkeypatch.setattr(svc.intel_repo, "list_active_stores", lambda tenant: STORES[:2])
    monkeypatch.setattr(svc.intel_repo, "resolve_mapped_stores", lambda tenant, sid, code, others: {
        "S-NMC": {"product_code": "77", "product_name": "D-PROTIN C"},
    })
    monkeypatch.setattr(svc.repo, "store_monthly_movement", lambda tenant, pairs, n: [
        {"store_id": "S-NMA", "ym": span[0], "qty_in": 2, "qty_out": 1, "stock": 4},
        {"store_id": "S-NMC", "ym": span[3], "qty_in": 0, "qty_out": 3, "stock": 9},
    ])
    out = svc.store_trends("T", "S-NMA", "5433")

    assert out["months"] == span[:-1] and len(out["months"]) == 4
    nma, nmc = out["stores"]
    assert nma["months"][0] == {"ym": span[0], "in": 2.0, "out": 1.0, "stock": 4.0}
    assert nmc["months"][3] == {"ym": span[3], "in": 0.0, "out": 3.0, "stock": 9.0}
    assert nmc["months"][0]["in"] is None
