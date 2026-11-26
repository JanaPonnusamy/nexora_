"""Product-grid identity. Same store + product code is one line.

A second supplier, a second store, or a different code is a different line.
Quantity on the surviving row is kept; copies are not added together.
DB-free: the ranking function is what the legacy grids apply after fetch,
and the workspace / assigned SQL is checked for the same rule.
"""

import inspect
import os
import sys

_BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.legacy_order.repository import assigned_orders  # noqa: E402
from modules.procurement.decision_repository import load_source  # noqa: E402
from modules.procurement.product_identity import (  # noqa: E402
    collapse_generated_payload,
    collapse_lines,
)
from modules.procurement.workspace_repository import (  # noqa: E402
    _FROM,
    _PRODUCT_RANK,
)


def _line(code, **extra):
    row = {"product_code": code, "store_id": "store-a", "final_qty": 4, "order_item_id": code}
    row.update(extra)
    return row


def test_api_response_returning_the_same_product_twice_keeps_one_line():
    first = _line("100", final_qty=4, order_item_id="item-1")
    copy = _line("100.0", final_qty=4, order_item_id="item-1")
    kept = collapse_lines([first, copy])
    assert len(kept) == 1
    assert kept[0]["final_qty"] == 4
    assert kept[0]["order_item_id"] == "item-1"


def test_refresh_loading_the_same_product_twice_does_not_add_quantities():
    loaded = _line("100", final_qty=6, assigned_qty=6, order_item_id="item-1")
    again = _line("100", final_qty=6, assigned_qty=6, order_item_id="item-1")
    kept = collapse_lines([loaded, again])
    assert len(kept) == 1
    assert kept[0]["final_qty"] == 6
    assert kept[0]["assigned_qty"] == 6


def test_same_product_in_two_snapshots_keeps_the_line_that_already_has_a_quantity():
    empty = _line("100", final_qty=0, suggested_qty=2, order_item_id="snap-1")
    reviewed = _line("100", final_qty=8, suggested_qty=2, order_item_id="snap-2")
    kept = collapse_lines([empty, reviewed])
    assert len(kept) == 1
    assert kept[0]["order_item_id"] == "snap-2"
    assert kept[0]["final_qty"] == 8


def test_same_medicine_with_different_supplier_mappings_stays_available():
    purani = _line("100", final_qty=5, supplier="Purani", SupplierProductCode="P-1", Stock=0)
    medley = _line("100", final_qty=5, supplier="Medley", SupplierProductCode="M-9", Stock=40)
    kept = collapse_lines([purani, medley], extra_fields=("supplier",))
    assert len(kept) == 2
    assert {row["supplier"] for row in kept} == {"Purani", "Medley"}
    # One supplier's several stock rows are one order line; the stockier mapping wins.
    low = _line("100", final_qty=5, SupplierProductCode="P-1", Stock=2, order_item_id="low")
    high = _line("100", final_qty=5, SupplierProductCode="P-2", Stock=20, order_item_id="high")
    one = collapse_lines([low, high])
    assert len(one) == 1
    assert one[0]["SupplierProductCode"] == "P-2"
    assert one[0]["final_qty"] == 5


def test_different_products_with_similar_names_stay_separate():
    rows = collapse_lines([
        _line("100", product_name="BRIV 25MG TAB", final_qty=2),
        _line("101", product_name="BRIV 25MG", final_qty=3),
    ])
    assert len(rows) == 2
    assert {row["product_code"] for row in rows} == {"100", "101"}


def test_same_product_in_different_stores_stays_separate():
    rows = collapse_lines([
        _line("100", store_id="nmw", final_qty=2),
        _line("100", store_id="nma", final_qty=9),
    ])
    assert len(rows) == 2
    assert {row["store_id"] for row in rows} == {"nmw", "nma"}
    assert {row["final_qty"] for row in rows} == {2, 9}


def test_repeated_fetch_appended_to_state_collapses_to_the_original_line():
    page = [_line("100", final_qty=4, order_item_id="item-1"), _line("200", final_qty=1, order_item_id="item-2")]
    appended = page + page
    kept = collapse_lines(appended)
    assert len(kept) == 2
    assert [row["order_item_id"] for row in kept] == ["item-1", "item-2"]
    assert [row["final_qty"] for row in kept] == [4, 1]


def test_selection_and_quantity_survive_on_the_kept_row():
    selected = _line(
        "100", final_qty=7, assigned_qty=7, order_item_id="selected",
        supplier="Purani",
    )
    duplicate = _line("100", final_qty=1, assigned_qty=0, order_item_id="copy")
    kept = collapse_lines([duplicate, selected])
    assert kept[0] is selected
    assert kept[0]["order_item_id"] == "selected"
    assert kept[0]["final_qty"] == 7
    assert kept[0]["supplier"] == "Purani"


def test_generated_order_keeps_the_demand_line_over_an_additional_copy():
    # ProductCode, WantedType, OrderQty — the insert payload positions used
    # by order_process (OrderQty is mapped before OrgOrderQty).
    demand = (100, "Auto", 6)
    additional = (100.0, "Additional Row", 0)
    other = (200, "Auto", 3)
    kept = collapse_generated_payload(
        [additional, demand, other],
        code_index=0, qty_index=2, wanted_index=1,
    )
    assert kept == [demand, other]


def test_workspace_query_cannot_multiply_a_line_through_the_product_master():
    assert "OUTER APPLY" in _FROM
    assert "LEFT JOIN sync.Products" not in _FROM
    assert "SELECT TOP 1" in _FROM
    assert "ROW_NUMBER()" in _PRODUCT_RANK
    assert "PARTITION BY oi.store_id" in _PRODUCT_RANK


def test_assigned_orders_query_picks_one_supplier_mapping():
    source = inspect.getsource(assigned_orders)
    assert "OUTER APPLY" in source
    assert "LEFT JOIN SupplierProductMatch" not in source
    assert "SPM.SupplierCode = om.OrSupplierCode" in source
    assert "ORDER BY ISNULL(SS.Stock, 0) DESC" in source


def test_generation_source_emits_one_master_row_per_store_and_code():
    source = inspect.getsource(load_source)
    assert "PARTITION BY p.store_id, p.ProductCode" in source
    assert "product_master_row = 1" in source
