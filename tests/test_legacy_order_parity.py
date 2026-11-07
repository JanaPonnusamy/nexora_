"""Golden comparison: legacy order SQL transcription vs Nexora refresh generation.

The legacy figures are a Python transcription of order_local.sql,
order_remote.sql, order_warehouse.sql, and the Additional Row zeroing in
order_process.py. SQL Server is not executed. Clause tests lock the
transcription to the SQL text that was read.
"""

import inspect
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement import decision_repository as repo  # noqa: E402
from modules.procurement import decision_rules as rules  # noqa: E402
from modules.procurement import decision_service  # noqa: E402
from modules.procurement import legacy_order_parity as parity  # noqa: E402

_SQL = Path(_BACKEND) / "modules" / "legacy_order" / "sql"
AS_OF = datetime(2026, 10, 25, 12, 0, 0)
MIN_DAYS = 13
MAX_DAYS = 18
RECENCY = 15


def _sql(name):
    return (_SQL / name).read_text(encoding="utf-8")


def _case(**overrides):
    base = {
        "window_sales_qty": 180,
        "line_frequency": 5,
        "max_line_qty": 20,
        "total_stock": 30,
        "sale_unit": 10,
        "last_sale": AS_OF - timedelta(days=2),
        "last_received": AS_OF - timedelta(days=10),
    }
    base.update(overrides)
    return base


def _buyer(case, mode="local", recency=RECENCY, min_days=MIN_DAYS, max_days=MAX_DAYS):
    return parity.buyer_result(
        case, mode=mode, min_days=min_days, max_days=max_days,
        recency_days=recency, as_of=AS_OF,
    )


def test_sql_clauses_local_remote_warehouse_are_not_the_same():
    local, remote, warehouse = _sql("order_local.sql"), _sql("order_remote.sql"), _sql("order_warehouse.sql")
    process = Path(_BACKEND, "modules", "legacy_order", "order_process.py").read_text(encoding="utf-8")
    for text in (local, remote, warehouse):
        assert "transactionvalidity = 0" in text
        assert "COUNT(DISTINCT ps.ID)" in text or "COUNT(DISTINCT ps.ID)" in text.replace(" ", "")
        assert "p.TotalStock" in text
        assert "@recencydays" in text
        assert "@minday" in text and "@maxday" in text
    assert "ps.quantity > 0" in local
    assert "NULLIF(ps.SaleUnit, 0)" in local
    assert "Transactiondate >= @ODATA" in local
    # Remote spike join is exclusive of the window boundary and does not null-guard SaleUnit.
    assert "psi.Transactiondate > @ODATA" in remote
    assert "NULLIF(ps.SaleUnit, 0)" not in remote
    assert "/ ps.SaleUnit" in remote
    assert "SeriesName = 'TO'" in warehouse
    assert "SeriesName = 'TO'" not in local
    assert "@recencydays + 10" in warehouse
    assert "WantedType = 'Additional Row'" in process
    assert "OrderQty = 0" in process


def test_loader_sql_uses_totalstock_line_frequency_and_producttrans_recency():
    source = inspect.getsource(repo.load_source)
    assert "p.TotalStock" in source
    assert "COUNT(DISTINCT ID)" in source
    assert "psi.Quantity > 0" in source
    assert "psi.TransactionValidity = 0" in source
    assert "psi.DontConsiderInOrder = 0" in source
    assert "LastBillDate" in source
    assert "LastGrnDate" in source
    assert "legacy_window_sales_qty" in source
    # The Nexora explainability stock expression stays available; order qty does not use it.
    assert "store_stock_expr" in source or "_store_stock_expr" in source


def test_local_spike_day_does_not_use_the_day_sum():
    """180 sold, max single line 20, stock 30, pack 10 → 1 pack.

    A max-day sum of 80 is not an input to this query. The older Nexora
    engine treats that day sum as a stock target and orders 5.
    """
    result = _buyer(_case(max_day_qty=80, max_bill_qty=80))
    assert result["orderable_packs"] == 1
    assert result["reason"] == "MAIN_LINE"
    assert result["min_qty"] == 36
    assert result["max_qty"] == 36

    nexora = rules.evaluate(
        {
            "is_active": True,
            "dont_consider": False,
            "window_sales_qty": 180,
            "max_day_sale_qty": 80,
            "max_bill_qty": 80,
            "max_line_sale_qty": 20,
            "billing_frequency": 5,
            "current_stock": 30,
            "sale_unit": 10,
            "last_sale_date": AS_OF - timedelta(days=2),
            "last_received_date": AS_OF - timedelta(days=10),
        },
        rules.DecisionParameters(
            rolling_days=90, min_days=13, max_days=18, recency_days=15, as_of=AS_OF,
        ),
    )
    assert nexora["suggested_qty"] != 1
    assert nexora["procurement_action"] == rules.ACTION_INCLUDE


def test_null_last_received_is_excluded_by_sql_comparison():
    result = _buyer(_case(last_received=None))
    assert result["orderable_packs"] == 0
    assert result["reason"] == "EXCLUDED_NO_SALE_SINCE_RECEIPT"


def test_sale_unit_zero_and_null_local_are_not_ordered():
    assert _buyer(_case(sale_unit=0))["reason"] == "EXCLUDED_SALE_UNIT"
    assert _buyer(_case(sale_unit=None))["orderable_packs"] == 0


def test_remote_sale_unit_zero_aborts_instead_of_ordering_zero():
    with pytest.raises(parity.LegacyRemoteQueryError):
        _buyer(_case(sale_unit=0), mode="remote")
    assert _buyer(_case(sale_unit=None), mode="remote")["orderable_packs"] == 0


def test_remote_and_local_packs_match_when_the_spike_input_matches():
    local = _buyer(_case())
    remote = _buyer(_case(), mode="remote")
    assert local["orderable_packs"] == remote["orderable_packs"] == 1


def test_remote_boundary_day_spike_is_a_different_input():
    """Same product, two aggregates: local keeps the @ODATA day, remote does not."""
    local = _buyer(_case(max_line_qty=80))
    remote = _buyer(_case(max_line_qty=20), mode="remote")
    assert local["orderable_packs"] == 5
    assert remote["orderable_packs"] == 1


def test_warehouse_pack_math_matches_local_on_the_same_aggregates():
    assert _buyer(_case())["orderable_packs"] == _buyer(_case(), mode="warehouse")["orderable_packs"]


def test_additional_row_is_inserted_then_zeroed():
    result = _buyer(_case(
        window_sales_qty=2, line_frequency=2, max_line_qty=1,
        total_stock=1, sale_unit=10,
    ))
    assert result["reason"] == "ADDITIONAL_ROW_ZEROED"
    assert result["sql_insert_packs"] == 1
    assert result["orderable_packs"] == 0
    assert result["auto_order"] is False


def test_recency_boundary_uses_datetime_subtraction():
    # Last receipt stays older than the sale, so only the recency cutoff differs.
    old_receipt = AS_OF - timedelta(days=40)
    kept = _buyer(_case(last_sale=AS_OF - timedelta(days=15), last_received=old_receipt))
    dropped = _buyer(_case(
        last_sale=AS_OF - timedelta(days=15, seconds=1), last_received=old_receipt,
    ))
    assert kept["orderable_packs"] == 1
    assert dropped["reason"] == "EXCLUDED_RECENCY"


def test_totalstock_not_stock_in_hand_sets_the_pack_count():
    """StockInHand 10 would order more; the query subtracts TotalStock 40."""
    result = _buyer(_case(total_stock=40, max_line_qty=80, line_frequency=2))
    # minqty = max(ceil(26), ceil(90)) = 90; maxqty = 80; 90 > 40 and (80-40)/10 = 4
    assert result["orderable_packs"] == 4
    hand = _buyer(_case(total_stock=10, max_line_qty=80, line_frequency=2))
    assert hand["orderable_packs"] == 7


def test_zero_sales_and_product_level_flag_are_not_invented():
    assert _buyer(_case(window_sales_qty=0))["reason"] == "EXCLUDED_NO_ELIGIBLE_SALES"
    # A product-level dont-consider flag is not in the order SELECT. Callers
    # that already dropped those sale lines pass window 0.


def test_pending_is_not_a_term():
    # No pending argument exists. Identical stock and sales produce identical packs.
    first = _buyer(_case())
    second = _buyer(_case())
    assert first == second


class _Conn:
    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True

    def close(self):
        self.closed = True


def _refresh():
    return {
        "refresh_id": "R1", "cycle_id": "C1", "store_id": "S1",
        "rolling_days": 90, "min_days": 13, "max_days": 18,
        "snapshot_status": "Draft",
    }


def _patch_generation(monkeypatch, source_rows):
    monkeypatch.setattr(repo, "get_refresh_for_generation", lambda t, r: _refresh())
    monkeypatch.setattr(decision_service, "get_connection", lambda: _Conn())
    monkeypatch.setattr(repo, "mark_generating", lambda *a, **k: 1)
    monkeypatch.setattr(repo, "load_source", lambda *a, **k: source_rows)
    monkeypatch.setattr(repo, "clear_products", lambda *a, **k: 0)
    captured = {}

    def _bulk(conn, rows):
        captured["rows"] = rows
        return len(rows)

    monkeypatch.setattr(repo, "bulk_insert_products", _bulk)
    monkeypatch.setattr(repo, "finalize", lambda *a, **k: None)
    return captured


def _source_row():
    return {
        "product_id": "P1",
        "product_code": "100",
        "product_name": "Spike",
        "is_active": True,
        "legacy_window_sales_qty": 180,
        "legacy_line_frequency": 5,
        "legacy_max_line_qty": 20,
        "total_stock": 30,
        "sale_unit": 10,
        "legacy_last_sale_date": AS_OF,
        "legacy_last_received_date": AS_OF - timedelta(days=10),
        # Nexora engine inputs that must not drive the default profile.
        "window_sales_qty": 180,
        "max_day_sale_qty": 80,
        "max_bill_qty": 80,
        "max_line_sale_qty": 80,
        "billing_frequency": 5,
        "current_stock": 10,
        "last_sale_date": AS_OF,
        "last_received_date": AS_OF - timedelta(days=1),
    }


def test_generate_vpl_default_profile_matches_legacy_local_not_evaluate(monkeypatch):
    monkeypatch.delenv("PROCUREMENT_GENERATION_PROFILE", raising=False)
    monkeypatch.setenv("LEGACY_RECENCY_DAYS", "15")
    captured = _patch_generation(monkeypatch, [_source_row()])
    out = decision_service.generate_vpl("T1", "R1")
    assert out["parameters"]["generation_profile"] == "legacy_local"
    assert out["generated_product_count"] == 1
    assert captured["rows"][0]["suggested_qty"] == 1
    assert captured["rows"][0]["current_stock_qty"] == 30
    assert captured["rows"][0]["reason_code"] == "MAIN_LINE"


def test_generate_vpl_nexora_profile_is_the_rollback(monkeypatch):
    monkeypatch.setenv("PROCUREMENT_GENERATION_PROFILE", "nexora")
    captured = _patch_generation(monkeypatch, [_source_row()])
    out = decision_service.generate_vpl("T1", "R1")
    assert out["parameters"]["generation_profile"] == "nexora"
    assert captured["rows"][0]["suggested_qty"] != 1
    assert captured["rows"][0]["reason_code"] == rules.INCLUDED_BELOW_MIN_DAYS


def test_additional_row_is_on_the_vpl_and_not_an_order_quantity(monkeypatch):
    monkeypatch.delenv("PROCUREMENT_GENERATION_PROFILE", raising=False)
    row = _source_row()
    row.update({
        "legacy_window_sales_qty": 2,
        "legacy_line_frequency": 2,
        "legacy_max_line_qty": 1,
        "total_stock": 1,
    })
    captured = _patch_generation(monkeypatch, [row])
    decision_service.generate_vpl("T1", "R1")
    written = captured["rows"][0]
    assert written["reason_code"] == "ADDITIONAL_ROW_ZEROED"
    assert written["suggested_qty"] == 0
