"""modules.procurement.product_identity.collapse_lines -- the server-side
dedup that backend/modules/legacy_order/repository.py's row-fetchers
(assigned_orders, qty_check_rows, pending_order_rows, orders_by_supplier,
all_open_orderables, all_assigned_orders) all run through before
order_export.py builds the exported workbook.

Regression basis: Nov 13 NMW supplier exports (SRI MURUGAN MEDICAL
AGENCIES, THANTHAI PHARMA DISTRIBUTOR) shipped with the same product code
repeated 2-3 times at the SAME order quantity on every copy (e.g. ALDACTONE
25 three times at qty 24 each) -- a real over-ship/over-bill risk, not a
cosmetic grid issue. Those exports predate this file: collapse_lines() did
not exist yet when they were generated."""
from __future__ import annotations

from modules.procurement.product_identity import (
    canonical_product_code,
    collapse_lines,
    line_identity,
)


def test_exact_duplicate_rows_collapse_to_one():
    # The real production pattern: identical ProductCode, identical OrderQty,
    # repeated verbatim (e.g. an OUTER APPLY fan-out from several supplier
    # mappings for the same product).
    row = {"ProductCode": 3747.0, "ProductName": "ALDACTONE 25", "OrderQty": 24, "StoreName": "NMW"}
    rows = [dict(row), dict(row), dict(row)]
    out = collapse_lines(rows)
    assert len(out) == 1
    assert out[0]["OrderQty"] == 24


def test_float_and_int_product_codes_are_the_same_identity():
    a = {"ProductCode": 100.0, "OrderQty": 4, "StoreName": "NMW"}
    b = {"ProductCode": 100, "OrderQty": 4, "StoreName": "NMW"}
    out = collapse_lines([a, b])
    assert len(out) == 1


def test_different_snapshots_keep_the_line_with_the_real_quantity():
    empty = {"ProductCode": "100", "OrderQty": 0, "StoreName": "NMW"}
    reviewed = {"ProductCode": "100", "OrderQty": 8, "StoreName": "NMW"}
    out = collapse_lines([empty, reviewed])
    assert len(out) == 1
    assert out[0] is reviewed


def test_different_stores_stay_distinct():
    nmw = {"ProductCode": "100", "OrderQty": 5, "StoreName": "NMW"}
    nma = {"ProductCode": "100", "OrderQty": 9, "StoreName": "NMA"}
    out = collapse_lines([nmw, nma])
    assert len(out) == 2


def test_different_suppliers_stay_distinct_when_supplier_is_an_identity_field():
    purani = {"ProductCode": "100", "OrderQty": 5, "StoreName": "NMW", "OrSupplier": "Purani"}
    medley = {"ProductCode": "100", "OrderQty": 5, "StoreName": "NMW", "OrSupplier": "Medley"}
    out = collapse_lines([purani, medley], extra_fields=("OrSupplier",))
    assert len(out) == 2


def test_a_row_with_no_product_code_is_never_merged_into_another():
    a = {"ProductCode": None, "OrderQty": 1, "StoreName": "NMW", "order_item_id": "a"}
    b = {"ProductCode": None, "OrderQty": 1, "StoreName": "NMW", "order_item_id": "b"}
    out = collapse_lines([a, b])
    assert len(out) == 2


def test_quantity_is_never_summed_across_duplicate_copies():
    # Guards against a tempting-but-wrong "fix": summing qty across dup rows
    # instead of picking one. 24 + 24 + 24 must never appear anywhere.
    row = {"ProductCode": "3747", "OrderQty": 24, "StoreName": "NMW"}
    out = collapse_lines([dict(row), dict(row), dict(row)])
    assert len(out) == 1
    assert out[0]["OrderQty"] == 24


def test_prefers_the_row_already_assigned_a_quantity_over_an_unassigned_zero_copy():
    unassigned = {"ProductCode": "100", "assigned_qty": 0, "OrderQty": 0, "StoreName": "NMW"}
    assigned = {"ProductCode": "100", "assigned_qty": 7, "OrderQty": 7, "StoreName": "NMW"}
    out = collapse_lines([unassigned, assigned])
    assert out[0] is assigned


def test_prefers_the_higher_stock_supplier_mapping_when_otherwise_tied():
    low_stock = {"ProductCode": "100", "OrderQty": 7, "StoreName": "NMW", "SupplierStock": 1}
    high_stock = {"ProductCode": "100", "OrderQty": 7, "StoreName": "NMW", "SupplierStock": 30}
    out = collapse_lines([low_stock, high_stock])
    assert out[0] is high_stock


def test_canonical_product_code_normalizes_float_suffix_but_keeps_real_decimals():
    assert canonical_product_code(100.0) == "100"
    assert canonical_product_code("100.0") == "100"
    assert canonical_product_code(100) == "100"
    assert canonical_product_code(None) == ""
    assert canonical_product_code("5854133.0") == "5854133"


def test_collapse_lines_preserves_first_seen_order():
    rows = [
        {"ProductCode": "B", "OrderQty": 1, "StoreName": "NMW"},
        {"ProductCode": "A", "OrderQty": 1, "StoreName": "NMW"},
        {"ProductCode": "B", "OrderQty": 2, "StoreName": "NMW"},
    ]
    out = collapse_lines(rows)
    assert [r["ProductCode"] for r in out] == ["B", "A"]


def test_collapse_lines_handles_empty_and_none_input():
    assert collapse_lines([]) == []
    assert collapse_lines(None) == []


def test_line_identity_falls_back_to_lowercase_field_names():
    row = {"productcode": "200", "storename": "NMA"}
    assert line_identity(row) == ("product", "NMA", "200")
