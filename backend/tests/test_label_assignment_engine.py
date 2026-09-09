"""Unit tests for the Label Exporter location-assignment engine.

These cover the box-allocation business rules directly (no DB), matching the
owner's acceptance cases in the redesign spec (§AH tests 1-8) plus the
guard-rail validation. The engine is pure, so every rule is asserted here in
isolation before any endpoint or UI touches it.
"""

import pytest

from modules.label_exporter.assignment_engine import (
    AssignmentError,
    Product,
    format_tab_box,
    parse_tab_box,
    plan_continue,
    plan_new_label,
    plan_single_boxes,
    plan_syp,
    validate_plan,
)


def _products(*names):
    """Build products with deterministic codes from a list of names."""
    return [Product(product_code=f"P{i:04d}", product_name=n) for i, n in enumerate(names, 1)]


def _boxes(plan):
    """{box_id: added_count} for compact assertions."""
    return {b.box: b.added for b in plan.boxes}


# --------------------------------------------------------------------------
# formatting helpers
# --------------------------------------------------------------------------

def test_format_tab_box_is_three_digit():
    assert format_tab_box("A", 1) == "A001"
    assert format_tab_box("a", 25) == "A025"
    assert format_tab_box("A", 123) == "A123"


def test_parse_tab_box_roundtrip_and_rejects_non_tab():
    assert parse_tab_box("A075") == ("A", 75)
    assert parse_tab_box("SYPA") is None      # SYP bucket, not a TAB box
    assert parse_tab_box("") is None
    assert parse_tab_box("AB12") is None


# --------------------------------------------------------------------------
# TEST 1 — TAB, new label, 14 Y products -> 2 boxes x 7
# --------------------------------------------------------------------------

def test_new_label_14_products_two_full_boxes():
    plan = plan_new_label("A", _products(*[f"A PROD {i:02d}" for i in range(14)]))
    validate_plan(plan)
    assert _boxes(plan) == {"A001": 7, "A002": 7}


# --------------------------------------------------------------------------
# TEST 2 — TAB, new label, 15 Y products -> 7 + 7 + 1
# --------------------------------------------------------------------------

def test_new_label_15_products_seven_seven_one():
    plan = plan_new_label("A", _products(*[f"A PROD {i:02d}" for i in range(15)]))
    validate_plan(plan)
    assert _boxes(plan) == {"A001": 7, "A002": 7, "A003": 1}


def test_new_label_sorts_by_name():
    plan = plan_new_label("A", _products("A ZEBRA", "A APPLE", "A MANGO"))
    names_in_order = [a.product_name for a in plan.assignments]
    assert names_in_order == ["A APPLE", "A MANGO", "A ZEBRA"]


# --------------------------------------------------------------------------
# TEST 3 — Existing A075 = 3, new 20 -> A075+4, A076+7, A077+7, A078+2
# --------------------------------------------------------------------------

def test_continue_fills_partial_box_first():
    existing = {"A001": 7, "A074": 7, "A075": 3}
    plan = plan_continue("A", _products(*[f"A NEW {i:02d}" for i in range(20)]), existing)
    validate_plan(plan)
    assert _boxes(plan) == {"A075": 4, "A076": 7, "A077": 7, "A078": 2}
    # the partial box is reported with its prior occupancy so the preview is honest
    a075 = next(b for b in plan.boxes if b.box == "A075")
    assert a075.existing == 3 and a075.total == 7


# --------------------------------------------------------------------------
# TEST 4 — Existing A075 = 7 (full), new 5 -> A076+5
# --------------------------------------------------------------------------

def test_continue_skips_full_last_box():
    existing = {"A075": 7}
    plan = plan_continue("A", _products(*[f"A NEW {i:02d}" for i in range(5)]), existing)
    validate_plan(plan)
    assert _boxes(plan) == {"A076": 5}


def test_continue_with_no_existing_starts_at_one():
    plan = plan_continue("B", _products("B ONE", "B TWO"), {})
    assert _boxes(plan) == {"B001": 2}


def test_continue_ignores_other_letters_boxes():
    # C-letter boxes must not influence A's numbering
    existing = {"C010": 7, "A002": 4}
    plan = plan_continue("A", _products("A NEW1", "A NEW2", "A NEW3", "A NEW4"), existing)
    assert _boxes(plan) == {"A002": 3, "A003": 1}


# --------------------------------------------------------------------------
# TEST 5 — New Label ignores existing occupancy entirely
# --------------------------------------------------------------------------

def test_new_label_ignores_existing_locations():
    # Even with A001-A020 populated, New Label starts a fresh A001 sequence.
    plan = plan_new_label("A", _products(*[f"A NEW {i:02d}" for i in range(20)]))
    assert _boxes(plan) == {"A001": 7, "A002": 7, "A003": 6}


# --------------------------------------------------------------------------
# TEST 7 — SYP -> SYP + first letter of product name
# --------------------------------------------------------------------------

def test_syp_buckets_by_first_letter():
    plan = plan_syp(_products("ASTHALIN SYP", "AMOXIL SYP", "BENADRYL SYP", "CROCIN SYP"))
    validate_plan(plan)
    assert _boxes(plan) == {"SYPA": 2, "SYPB": 1, "SYPC": 1}


def test_syp_has_no_capacity_limit():
    plan = plan_syp(_products(*[f"A SYP {i:02d}" for i in range(20)]))
    validate_plan(plan)  # 20 in one SYPA bucket must not trip capacity guard
    assert _boxes(plan) == {"SYPA": 20}


# --------------------------------------------------------------------------
# TEST 8 — Single product box: one product, one box
# --------------------------------------------------------------------------

def test_single_product_boxes_one_each():
    plan = plan_single_boxes("D", _products("DOLO 650", "DERIPHYLLIN"), {})
    validate_plan(plan)
    # sorted by name: DERIPHYLLIN then DOLO 650
    assert [a.box for a in plan.assignments] == ["D001", "D002"]
    assert all(b.added == 1 for b in plan.boxes)


def test_single_product_box_continues_after_existing():
    plan = plan_single_boxes("D", _products("DOLO 650"), {"D005": 1})
    assert _boxes(plan) == {"D006": 1}


# --------------------------------------------------------------------------
# guard rails (spec §AF)
# --------------------------------------------------------------------------

def test_validate_rejects_overfilled_tab_box():
    plan = plan_new_label("A", _products(*[f"A {i}" for i in range(7)]))
    # force an 8th product into the same box to simulate a bad plan
    from modules.label_exporter.assignment_engine import Assignment
    plan.assignments.append(Assignment("PX", "A EXTRA", "A001", 8))
    plan.boxes[0].added += 1
    with pytest.raises(AssignmentError):
        validate_plan(plan)


def test_validate_rejects_duplicate_product():
    plan = plan_new_label("A", _products("A ONE"))
    from modules.label_exporter.assignment_engine import Assignment
    plan.assignments.append(Assignment(plan.assignments[0].product_code, "A ONE", "A001", 2))
    with pytest.raises(AssignmentError):
        validate_plan(plan)


def test_empty_input_raises():
    with pytest.raises(AssignmentError):
        plan_new_label("A", [])
