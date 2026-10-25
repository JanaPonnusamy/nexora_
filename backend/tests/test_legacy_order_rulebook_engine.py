"""Rule-book order engine (rulebook_order.py): profile T decisions mapped onto
the exact columns order_process.insert_data_into_destination stores, so a
rule-book order lands in the same OrderManagement tables as a legacy one."""
from __future__ import annotations

import datetime

from modules.legacy_order import order_process, rulebook_order as rb

AS_OF = datetime.datetime(2026, 10, 25, 18, 0, 0)
PARAMS = dict(rb.DEFAULT_PARAMS)


def _row(code, **kw):
    base = {
        "ProductCode": code, "ProductName": f"P{code}", "TotalStock": 30.0, "SaleUnit": 10.0,
        "PurchasePrice": 5.0, "MRP": 9.0, "UnitDescription": "TAB", "SubLocation": "A1", "ProductType": 1,
        "window_qty": 180.0, "bill_frequency": 4, "line_frequency": 9, "max_bill_qty": 60.0,
        "max_day_qty": 80.0, "max_day_date": datetime.date(2026, 10, 20),
        "last_sale": AS_OF - datetime.timedelta(days=2), "last_received": AS_OF - datetime.timedelta(days=20),
    }
    base.update(kw)
    return base


def test_worked_example_orders_five_packs_set_by_max_day():
    # Rule book worked example: gross MAX(36, 60, 80, 45) = 80, net 50, pack 10 -> 5.
    (d,) = rb.evaluate_rows([_row(1)], PARAMS, AS_OF)
    assert d["result"]["reason"] == "AUTO" and d["result"]["packs"] == 5
    assert d["result"]["determinant"] == "max_day"


def test_order_rows_match_the_order_process_columns():
    decisions = rb.evaluate_rows([
        _row(1),
        _row(2, last_sale=AS_OF - datetime.timedelta(days=40)),           # no sale in 15 days
        _row(3, TotalStock=500.0),                                         # stock covers target
        _row(4, SaleUnit=None),                                            # blocked
    ], PARAMS, AS_OF)
    columns, rows = rb.order_rows(decisions, PARAMS, "NMW", "5", AS_OF)
    expected = {src.lower() for src, _ in order_process.COLUMN_MAP}
    assert expected <= {c.lower() for c in columns}
    assert len(rows) == 1
    line = dict(zip(columns, rows[0]))
    assert line["productcode"] == 1 and line["OrderQty"] == 5
    assert line["OrderId"] == "20261025180000" and line["storename"] == "NMW" and line["Status"] == 0
    assert line["MaxQty"] == 80 and line["WantedType"] == rb.WANTED["max_day"]
    assert line["productTypeName"] == "Pharma"


def test_rare_mover_is_one_pack_for_manual_review():
    row = _row(5, TotalStock=1.0, window_qty=2.0, bill_frequency=2, line_frequency=2,
               max_bill_qty=1.0, max_day_qty=1.0, SaleUnit=10.0,
               last_received=AS_OF - datetime.timedelta(days=30))
    decisions = rb.evaluate_rows([row], PARAMS, AS_OF)
    columns, rows = rb.order_rows(decisions, PARAMS, "NMW", "5", AS_OF)
    line = dict(zip(columns, rows[0]))
    assert line["OrderQty"] == 1 and line["WantedType"] == rb.WANTED_RARE


def test_registry_params_change_the_quantity():
    (d,) = rb.evaluate_rows([_row(6, max_day_qty=0.0, max_bill_qty=0.0, bill_frequency=90, TotalStock=0.0)],
                            {**PARAMS, "max_days": 36}, AS_OF)
    # 180/90 = 2 a day x 36 days = 72 -> 8 packs of 10.
    assert d["result"]["packs"] == 8 and d["result"]["determinant"] == "cover"
