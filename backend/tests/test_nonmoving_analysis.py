"""Non-Moving Stock Analysis -- classification, valuation, cross-store and
transfer rules over synthetic snapshot rows (no database). Each test names the
acceptance case it covers."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from modules.nonmoving_analysis import service as svc

TODAY = date(2026, 11, 1)
CFG = svc.Config()


def raw(code="1", stock=10.0, batch_stock=None, sale_days=None, **kw):
    """A store_snapshot row; sale_days = days since the last valid PSI sale."""
    row = {
        "product_code": code, "product_name": f"PRODUCT {code}", "unit": "TAB", "pack": "10",
        "sale_unit": 1.0, "product_type": 1, "is_active": 1, "created_date": None, "mrp": 10.0,
        "stock": stock, "batch_stock": stock if batch_stock is None else batch_stock,
        "batch_count": 1, "cost_value": stock * 5.0, "ptr_value": stock * 6.0, "mrp_value": stock * 10.0,
        "expired_qty": 0.0, "expired_value": 0.0, "near_expiry_qty": 0.0, "near_expiry_value": 0.0,
        "no_expiry_batches": 0, "earliest_expiry": TODAY + timedelta(days=400),
        "last_sale_psi": TODAY - timedelta(days=sale_days) if sale_days is not None else None,
        "last_sale_rollup": TODAY - timedelta(days=sale_days) if sale_days is not None else None,
        "last_sale_batch": None,
        "sales_30": 0.0, "sales_90": 0.0, "sales_180": 0.0, "bills_90": 0, "invalid_lines_180": 0,
        "last_purchase_date": TODAY - timedelta(days=400), "last_grn_date": TODAY - timedelta(days=400),
        "first_receipt_date": TODAY - timedelta(days=800), "supplier_code": "S1", "supplier_name": "SUP ONE",
    }
    row.update(kw)
    return row


def a(**kw):
    return svc.analyse(raw(**kw), CFG, TODAY)


@pytest.mark.parametrize("days,cls", [
    (0, "ACTIVE"), (30, "ACTIVE"), (31, "SLOW"), (60, "SLOW"), (61, "VERY_SLOW"), (90, "VERY_SLOW"),
    (91, "NM_RISK"), (180, "NM_RISK"), (181, "NON_MOVING"), (365, "NON_MOVING"), (366, "DEAD"), (900, "DEAD"),
])
def test_classification_bands(days, cls):
    # Cases 1-4: active, 90, 180 and > 365 days without a sale.
    r = a(sale_days=days)
    assert r["classification"] == cls and r["days_since_sale"] == days
    assert r["non_moving"] == (cls in ("NM_RISK", "NON_MOVING", "DEAD"))


def test_custom_bands():
    cfg = svc.parse_config("15,45,75,150,300")
    assert svc.analyse(raw(sale_days=46), cfg, TODAY)["classification"] == "VERY_SLOW"
    with pytest.raises(HTTPException):
        svc.parse_config("30,20,90,180,365")


def test_zero_stock_is_not_valued():
    # Case 5: zero stock never contributes value; batch stock left over is flagged.
    r = a(stock=0.0, batch_stock=4.0, cost_value=20.0, sale_days=200)
    assert not r["in_stock"] and not r["non_moving"]
    assert r["cost_value"] == 0 and r["mrp_value"] == 0
    assert "STOCK_MISMATCH" in r["flags"]
    assert svc.store_kpis([r])["non_moving_value"] == 0


def test_no_sales_history_vs_new_product():
    # Case 6 + newly introduced products are never dead stock.
    old = a(sale_days=None, first_receipt_date=TODAY - timedelta(days=300))
    new = a(sale_days=None, first_receipt_date=TODAY - timedelta(days=20))
    assert old["classification"] == "NO_SALES" and old["non_moving"]
    assert new["classification"] == "NEW" and not new["non_moving"]


def test_missing_transaction_history_is_flagged_not_assumed():
    # Case 7: nothing in any source -> NO_SALES with NO_TXN_HISTORY, never a made-up date.
    r = a(sale_days=None, first_receipt_date=None, last_purchase_date=None, last_grn_date=None)
    assert r["classification"] == "NO_SALES" and r["last_sale_date"] is None
    assert "NO_TXN_HISTORY" in r["flags"]


def test_last_sale_falls_back_to_rollup_then_batch_and_flags_conflict():
    roll = a(sale_days=None, last_sale_rollup=TODAY - timedelta(days=700))
    assert roll["last_sale_source"] == "ROLLUP" and roll["classification"] == "DEAD"
    assert "LAST_SALE_FROM_ROLLUP" in roll["flags"]
    bat = a(sale_days=None, last_sale_batch=TODAY - timedelta(days=100))
    assert bat["last_sale_source"] == "BATCH" and bat["classification"] == "NM_RISK"
    conflict = a(sale_days=10, last_sale_rollup=TODAY - timedelta(days=5))
    assert conflict["last_sale_source"] == "PSI" and conflict["days_since_sale"] == 10
    assert "SALE_DATE_CONFLICT" in conflict["flags"]


def test_last_purchase_is_never_used_as_last_sale():
    r = a(sale_days=None, last_purchase_date=TODAY - timedelta(days=5), first_receipt_date=TODAY - timedelta(days=500))
    assert r["last_sale_date"] is None and r["classification"] == "NO_SALES"


def test_batches_and_expiry_status():
    # Cases 8 + 9: several batches, some expired / near expiry.
    expired = a(sale_days=200, batch_count=3, expired_qty=4.0, expired_value=20.0, near_expiry_qty=2.0)
    assert expired["expiry_status"] == "Expired" and expired["expired_value"] == 20.0
    near = a(sale_days=200, batch_count=2, near_expiry_qty=2.0, near_expiry_value=10.0)
    assert near["expiry_status"] == "Near expiry"
    assert a(batch_count=0, sale_days=5)["expiry_status"] == "No batch"
    k = svc.store_kpis([expired, near])
    assert k["expiry_risk_value"] == 30.0


def test_stock_mismatch_and_invalid_sales_flags():
    # Cases 12 + 13.
    r = a(stock=10.0, batch_stock=7.0, sale_days=100, invalid_lines_180=3)
    assert "STOCK_MISMATCH" in r["flags"] and "INVALID_SALES" in r["flags"]


def _net(stores, adj_pairs):
    meta = {s: {"store_id": s, "store_code": s, "store_name": s} for s in stores}
    adj = {}
    for (sa, ca), (sb, cb) in adj_pairs:
        adj.setdefault((sa, ca), {}).setdefault(sb, {})[cb] = 99.0
        adj.setdefault((sb, cb), {}).setdefault(sa, {})[ca] = 99.0
    return svc.Network(stores=[meta[s] for s in stores], meta=meta, rows={s: {} for s in stores}, adj=adj)


def put(net, store, **kw):
    r = svc.analyse(raw(**kw), CFG, TODAY)
    net.rows[store][r["product_code"]] = r
    return r


def selling(code, stock, sales_90, sale_days=2, bills=6, **kw):
    return dict(code=code, stock=stock, sale_days=sale_days, sales_90=sales_90, sales_30=sales_90 / 3,
                bills_90=bills, **kw)


def test_prompt_example_transfer():
    # Case 10 + 11: this store 35 units dead; NMC and NMV selling, NMG also idle.
    net = _net(["HERE", "NMC", "NMV", "NMG"], [
        (("HERE", "1"), ("NMC", "11")), (("HERE", "1"), ("NMV", "21")), (("HERE", "1"), ("NMG", "31")),
    ])
    put(net, "HERE", code="1", stock=35.0, sale_days=200)
    put(net, "NMC", **selling("11", stock=15.0, sales_90=90))   # target 30 -> need 15
    put(net, "NMV", **selling("21", stock=10.0, sales_90=60))   # target 20 -> need 10
    put(net, "NMG", code="31", stock=19.0, sale_days=150)      # non-moving: never a destination
    recs, blocks = svc.transfer_plan(net, CFG)
    got = {(r["source_store"], r["dest_store"]): r["suggested_qty"] for r in recs}
    assert got == {("HERE", "NMC"): 15, ("HERE", "NMV"): 10}
    here_nmc = next(r for r in recs if r["dest_store"] == "NMC")
    assert here_nmc["source_after"] == 20 and here_nmc["dest_after"] == 30
    assert "ceil(90 / 90 x 30) = 30" in here_nmc["calculation"]
    # NMG is non-moving too, but its peers (HERE only) have no demand.
    assert any(b["store_code"] == "NMG" for b in blocks)
    other = svc.cross_store_rows(net, "HERE", "1")
    assert [c["store_code"] for c in other] == ["HERE", "NMC", "NMG", "NMV"]


def test_destination_need_is_not_double_allocated():
    net = _net(["A", "B", "D"], [(("A", "1"), ("D", "9")), (("B", "2"), ("D", "9"))])
    put(net, "A", code="1", stock=50.0, sale_days=400)
    put(net, "B", code="2", stock=50.0, sale_days=200)
    put(net, "D", **selling("9", stock=0.0, sales_90=30))     # need 10
    recs, _ = svc.transfer_plan(net, CFG)
    assert [(r["source_store"], r["suggested_qty"]) for r in recs] == [("A", 10)]   # oldest stock first


def test_no_eligible_destination_reasons():
    # Case 14.
    net = _net(["A", "B", "C", "U"], [(("A", "1"), ("B", "2")), (("A", "1"), ("C", "3"))])
    put(net, "A", code="1", stock=20.0, sale_days=300)
    put(net, "B", code="2", stock=100.0, sale_days=5, sales_90=30, sales_30=10, bills_90=5)   # covered
    put(net, "C", code="3", stock=0.0, sale_days=60, sales_90=3, bills_90=1)                 # stale demand
    put(net, "U", code="7", stock=5.0, sale_days=None)                                       # unmapped
    recs, blocks = svc.transfer_plan(net, CFG)
    assert recs == []
    by = {b["store_code"]: b for b in blocks}
    assert by["A"]["reason"] == "no mapped store has verified demand needing stock"
    assert any(d.startswith("B: already holds") for d in by["A"]["details"])
    assert by["U"]["reason"] == "not mapped to any other store"


def test_transfer_safety_rules():
    net = _net(["A", "D", "P"], [(("A", "1"), ("D", "9")), (("P", "5"), ("D", "8"))])
    # Only 4 of 20 units are safe to move: 10 expired, 6 near expiry.
    put(net, "A", code="1", stock=20.0, sale_days=300, expired_qty=10.0, near_expiry_qty=6.0)
    put(net, "D", **selling("9", stock=0.0, sales_90=90))
    # Pack size differs between stores -> identity/unit not trusted.
    put(net, "P", code="5", stock=30.0, sale_days=300, sale_unit=10.0)
    put(net, "D", **selling("8", stock=0.0, sales_90=90))
    recs, blocks = svc.transfer_plan(net, CFG)
    assert [(r["source_store"], r["suggested_qty"]) for r in recs] == [("A", 4)]
    assert any(b["store_code"] == "P" and b["reason"].startswith("pack size differs") for b in blocks)


def test_whole_packs_and_ambiguous_identity():
    net = _net(["A", "D"], [(("A", "1"), ("D", "9")), (("A", "1"), ("D", "10"))])
    put(net, "A", code="1", stock=25.0, sale_days=300, sale_unit=10.0)
    put(net, "D", **selling("9", stock=0.0, sales_90=90, sale_unit=10.0))
    put(net, "D", **selling("10", stock=0.0, sales_90=90, sale_unit=10.0))
    recs, blocks = svc.transfer_plan(net, CFG)
    assert recs == [] and blocks[0]["reason"].startswith("product identity is ambiguous")
    assert svc._whole_packs(27, 10) == 20 and svc._whole_packs(7.6, 1) == 7


def test_moving_source_keeps_its_own_cover():
    net = _net(["A", "D"], [(("A", "1"), ("D", "9"))])
    # A still sells 30 / 90 days (keeps 30) but holds 100 -> 70 excess.
    put(net, "A", code="1", stock=100.0, sale_days=40, sales_90=30, bills_90=4)
    put(net, "D", **selling("9", stock=0.0, sales_90=270))     # need 90
    recs, _ = svc.transfer_plan(net, CFG)
    assert recs[0]["suggested_qty"] == 70 and recs[0]["source_keep"] == 30


def test_filters_and_paging():
    rows = [a(code=str(i), sale_days=d) for i, d in enumerate([5, 95, 200, 400, None])]
    rows.append(a(code="z", stock=0.0, sale_days=500))
    nm = svc.filter_rows(rows, non_moving_only=True)
    assert {r["product_code"] for r in nm} == {"1", "2", "3", "4"}
    assert [r["product_code"] for r in svc.filter_rows(rows, classes="DEAD")] == ["3"]
    assert {r["product_code"] for r in svc.filter_rows(rows, min_days=100)} == {"2", "3", "4"}
    page, total, _, _ = svc._page(svc.filter_rows(rows), "days_since_sale", "desc", 1, 2)
    assert total == 5 and [r["product_code"] for r in page] == ["4", "3"]   # never sold sorts oldest


def test_access_super_admin_all_stores_pm_own_store(monkeypatch):
    from modules.nonmoving_analysis import router as r
    monkeypatch.setattr(r.repo, "purchase_manager_store_ids",
                        lambda uid: ["S-NMC"] if uid == "U-PM" else [])
    # Super admin / platform user: every store.
    assert r._assert_allowed({"tenant_id": "T", "role_names": ["SUPER_ADMIN"]}, "T") is None
    assert r._assert_allowed({"tenant_id": None, "is_platform_user": True, "role_names": []}, "T") is None
    # Purchase manager: only their assigned store.
    scope = r._assert_allowed({"sub": "U-PM", "tenant_id": "T", "role_names": ["PURCHASE_MANAGER"]}, "T")
    assert scope == {"S-NMC"}
    r._check_store(scope, "s-nmc")
    with pytest.raises(HTTPException) as exc:
        r._check_store(scope, "S-NMA")
    assert exc.value.status_code == 403
    # PM with no assignment row falls back to the JWT store, else refused.
    assert r._assert_allowed({"sub": "U-X", "tenant_id": "T", "store_id": "s-nmg",
                              "role_names": ["PURCHASE_MANAGER"]}, "T") == {"S-NMG"}
    with pytest.raises(HTTPException):
        r._assert_allowed({"sub": "U-X", "tenant_id": "T", "role_names": ["PURCHASE_MANAGER"]}, "T")
    # Another tenant, or a non-PM role: refused.
    with pytest.raises(HTTPException):
        r._assert_allowed({"sub": "U-PM", "tenant_id": "OTHER", "role_names": ["PURCHASE_MANAGER"]}, "T")
    for roles in (["SALESMAN"], ["STORE_ADMIN"], ["TENANT_ADMIN"], ["STOCK_VIEWER"]):
        with pytest.raises(HTTPException) as exc:
            r._assert_allowed({"sub": "U-PM", "tenant_id": "T", "role_names": roles}, "T")
        assert exc.value.status_code == 403


def test_store_must_belong_to_tenant(monkeypatch):
    monkeypatch.setattr(svc.intel_repo, "list_active_stores",
                        lambda tenant: [{"store_id": "S-A", "store_code": "NMA", "store_name": "A"}] if tenant == "T" else [])
    assert svc._store_of("T", "s-a")["store_code"] == "NMA"
    with pytest.raises(HTTPException) as exc:
        svc._store_of("T", "S-FOREIGN")
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        svc._store_of("OTHER", "S-A")


def test_export_returns_every_row():
    rows = [a(code=str(i), sale_days=200) for i in range(1500)]
    page, total, _, size = svc._page(rows, "cost_value", "desc", 1, None)
    assert len(page) == total == size == 1500
    page, total, _, size = svc._page(rows, "cost_value", "desc", 1, 5000)
    assert len(page) == svc.MAX_PAGE and total == 1500


def test_active_stock_is_never_a_source():
    net = _net(["A", "D"], [(("A", "1"), ("D", "9"))])
    # Sold 14 days ago with little velocity: "excess" by the numbers, but Active.
    put(net, "A", code="1", stock=6.0, sale_days=14, sales_90=1, bills_90=1)
    put(net, "D", **selling("9", stock=0.0, sales_90=90))
    recs, blocks = svc.transfer_plan(net, CFG)
    assert recs == [] and blocks == []
