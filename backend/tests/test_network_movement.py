"""Network Movement Intelligence — pure-Python tests (no database).

Covers the union-find grouping predicate and the aggregation math in
modules/procurement/network_movement_service.py. Mirrors the worked example
from the design review (NMA=0, NMW=35, NMC=12, NMS=18 -> network=65).
"""

import sys
import os
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.procurement import network_movement_service as svc
from modules.procurement import decision_rules as rules

NMA, NMW, NMC, NMS, NMG = "store-a", "store-w", "store-c", "store-s", "store-g"


def _edge(src_store, src_code, tgt_store, tgt_code, confidence=98.0, method="SUPPLIER"):
    return {
        "source_store_id": src_store, "source_product_code": src_code,
        "target_store_id": tgt_store, "target_product_code": tgt_code,
        "confidence": confidence, "match_method": method,
    }


def _metrics(sales_qty=0.0, stock=0.0, avg_sale=None, last_sale=None):
    return {
        "sales_qty": sales_qty, "stock": stock,
        "avg_sale": avg_sale if avg_sale is not None else sales_qty / 90,
        "last_sale_date": last_sale,
    }


# --------------------------------------------------------------------------
# Grouping (union-find over presence, not VPL demand)
# --------------------------------------------------------------------------

def test_grouping_merges_only_mapped_products():
    nodes = [(NMA, "P1"), (NMW, "P2"), (NMC, "P3")]
    mappings = [
        _edge(NMA, "P1", NMW, "P2"),
        _edge(NMW, "P2", NMC, "P3"),
    ]
    groups, _ = svc._group_by_presence(nodes, mappings)
    # All three nodes land in one component.
    assert len(groups) == 1
    (only_group,) = groups.values()
    assert set(only_group) == set(nodes)


def test_unmapped_product_is_never_merged():
    """Case F/H of the design review: no mapping edge -> stays its own
    single-node component, never guessed into a group."""
    nodes = [(NMA, "P1"), (NMW, "UNRELATED")]
    groups, _ = svc._group_by_presence(nodes, mappings=[])
    assert len(groups) == 2
    for group_nodes in groups.values():
        assert len(group_nodes) == 1


def test_ambiguous_mapping_does_not_cross_contaminate_other_products():
    """A mapping edge for one product must not merge an unrelated product that
    happens to share a store — union-find only follows explicit edges."""
    nodes = [(NMA, "P1"), (NMW, "P2"), (NMA, "OTHER"), (NMW, "OTHER2")]
    mappings = [_edge(NMA, "P1", NMW, "P2")]
    groups, _ = svc._group_by_presence(nodes, mappings)
    sizes = sorted(len(g) for g in groups.values())
    assert sizes == [1, 1, 2]


def test_confidence_is_the_weakest_edge_in_the_group():
    nodes = [(NMA, "P1"), (NMW, "P2"), (NMC, "P3")]
    mappings = [
        _edge(NMA, "P1", NMW, "P2", confidence=99.0),
        _edge(NMW, "P2", NMC, "P3", confidence=61.0),
    ]
    groups, edge_stats = svc._group_by_presence(nodes, mappings)
    (root,) = groups.keys()
    assert edge_stats[root]["confidence"] == 61.0


# --------------------------------------------------------------------------
# Aggregation (the worked example from the design review)
# --------------------------------------------------------------------------

def test_network_sales_is_the_sum_across_mapped_stores():
    """NMA=0, NMW=35, NMC=12, NMS=18 -> network=65 (NMG absent/unmapped)."""
    nodes = [(NMA, "A1"), (NMW, "W1"), (NMC, "C1"), (NMS, "S1")]
    mappings = [
        _edge(NMA, "A1", NMW, "W1"),
        _edge(NMW, "W1", NMC, "C1"),
        _edge(NMC, "C1", NMS, "S1"),
    ]
    metrics_by_store = {
        NMA: {"A1": _metrics(sales_qty=0.0, stock=2.0)},
        NMW: {"W1": _metrics(sales_qty=35.0, stock=4.0)},
        NMC: {"C1": _metrics(sales_qty=12.0, stock=6.0)},
        NMS: {"S1": _metrics(sales_qty=18.0, stock=3.0)},
    }
    groups, edge_stats = svc._group_by_presence(nodes, mappings)
    rows = svc._build_rows("tenant-x", groups, edge_stats, metrics_by_store, rolling_days=90)

    assert len(rows) == 4  # one row per mapped store
    assert all(r["network_sales_qty"] == 65.0 for r in rows)
    assert all(r["mapped_store_count"] == 4 for r in rows)
    assert all(r["active_store_count"] == 3 for r in rows)  # NMA had 0 sales


def test_local_non_moving_can_still_be_network_fast():
    """The flagship case: NMA never sells it, NMW/NMC/NMS do -> network FAST,
    even though NMA's own avg_daily_sales is 0 (NONMOVING)."""
    nodes = [(NMA, "A1"), (NMW, "W1"), (NMC, "C1"), (NMS, "S1")]
    mappings = [
        _edge(NMA, "A1", NMW, "W1"),
        _edge(NMW, "W1", NMC, "C1"),
        _edge(NMC, "C1", NMS, "S1"),
    ]
    metrics_by_store = {
        NMA: {"A1": _metrics(sales_qty=0.0, stock=2.0, avg_sale=0.0)},
        NMW: {"W1": _metrics(sales_qty=3200.0, stock=4.0, avg_sale=55.0)},
        NMC: {"C1": _metrics(sales_qty=1080.0, stock=6.0, avg_sale=12.0)},
        NMS: {"S1": _metrics(sales_qty=1620.0, stock=3.0, avg_sale=18.0)},
    }
    groups, edge_stats = svc._group_by_presence(nodes, mappings)
    rows = svc._build_rows("tenant-x", groups, edge_stats, metrics_by_store, rolling_days=90)

    local_class_nma = rules.movement_class(0.0, svc._CLASS_PARAMS)
    assert local_class_nma == "NONMOVING"

    nma_row = next(r for r in rows if r["store_id"] == NMA)
    assert nma_row["network_movement_class"] == "FAST"
    assert nma_row["fast_store_count"] >= 1
    # This is exactly the row Network Opportunities looks for: local NONMOVING,
    # network FAST, product present locally (stock=2 > 0).
    assert nma_row["local_movement_class"] == "NONMOVING"
    assert nma_row["local_sales_qty"] == 0.0
    assert nma_row["local_stock_qty"] == 2.0

    nmw_row = next(r for r in rows if r["store_id"] == NMW)
    assert nmw_row["local_movement_class"] == "FAST"
    assert nmw_row["local_sales_qty"] == 3200.0


def test_single_store_component_is_dropped_not_persisted():
    """An unmapped product with real presence forms its own component but adds
    no information beyond the local store's own movement_class — must not be
    written (keeps the cache to genuinely cross-store rows only)."""
    nodes = [(NMA, "SOLO")]
    metrics_by_store = {NMA: {"SOLO": _metrics(sales_qty=40.0, stock=1.0)}}
    groups, edge_stats = svc._group_by_presence(nodes, mappings=[])
    rows = svc._build_rows("tenant-x", groups, edge_stats, metrics_by_store, rolling_days=90)
    assert rows == []


def test_network_movement_class_reuses_local_thresholds_exactly():
    """No second classification algorithm — same FAST/MEDIUM/SLOW/NONMOVING
    cut-offs as decision_rules.movement_class."""
    assert svc._CLASS_PARAMS.movement_fast_cut == 50.0
    assert svc._CLASS_PARAMS.movement_medium_cut == 10.0
    assert rules.movement_class(50.0, svc._CLASS_PARAMS) == "FAST"
    assert rules.movement_class(49.999, svc._CLASS_PARAMS) == "MEDIUM"
    assert rules.movement_class(0.0, svc._CLASS_PARAMS) == "NONMOVING"


def test_network_last_sale_date_is_the_latest_across_the_group():
    nodes = [(NMA, "A1"), (NMW, "W1")]
    mappings = [_edge(NMA, "A1", NMW, "W1")]
    metrics_by_store = {
        NMA: {"A1": _metrics(sales_qty=5.0, last_sale=date(2026, 1, 10))},
        NMW: {"W1": _metrics(sales_qty=5.0, last_sale=date(2026, 3, 1))},
    }
    groups, edge_stats = svc._group_by_presence(nodes, mappings)
    rows = svc._build_rows("tenant-x", groups, edge_stats, metrics_by_store, rolling_days=90)
    assert all(r["network_last_sale_date"] == date(2026, 3, 1) for r in rows)


if __name__ == "__main__":
    failures = 0
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERROR {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
