"""Service-layer tests for the Label Exporter assignment planner.

The repository is monkeypatched (no database) so we can assert the
backend-authoritative behaviour of _build_assignment_plan / preview / commit:
the corrected-unit path (spec Test 6), tenant/store safety (spec Test 12), and
that commit writes exactly the planned assignments.
"""

import pytest
from fastapi import HTTPException

from modules.label_exporter import service


@pytest.fixture
def fake_repo(monkeypatch):
    """A stand-in repository whose product set + occupancy are controlled per
    test. Records what assign_locations was asked to commit."""

    class Repo:
        def __init__(self):
            self.products = {}     # code -> row dict
            self.occupancy = {}    # box -> count
            self.committed = None

        def ensure_schema(self):
            pass

        def get_products_for_assignment(self, tenant_id, store_id, codes):
            return [self.products[c] for c in codes if c in self.products]

        def get_box_occupancy(self, tenant_id, store_id, letter, exclude_codes=()):
            return dict(self.occupancy)

        def assign_locations(self, tenant_id, store_id, enriched, mode, atype, user_id):
            self.committed = {"rows": enriched, "mode": mode, "type": atype, "user": user_id}
            return {"assigned": len(enriched)}

    repo = Repo()
    monkeypatch.setattr(service, "repository", repo)
    return repo


def _prod(code, name, unit, loc=None, stock=0):
    return {
        "product_code": code,
        "product_name": name,
        "unit_description": unit,
        "current_location": loc,
        "stock": stock,
    }


# --------------------------------------------------------------------------
# TEST 6 — CALPOL old unit SYP, corrected to TAB -> TAB box, not SYP bucket
# --------------------------------------------------------------------------

def test_corrected_unit_tab_uses_tab_rule(fake_repo):
    # The repo already resolves the corrected unit (TAB) for CALPOL.
    fake_repo.products = {"C1": _prod("C1", "CALPOL", "TAB")}
    result = service.preview_assignment(
        "t", "s", unit="TAB", mode="new_label", assignment_type="standard_box",
        letter="C", product_codes=["C1"], start_number=1,
    )
    assert result["assignments"][0]["box"] == "C001"      # TAB box, 3-digit
    assert result["unit"] == "TAB"


# --------------------------------------------------------------------------
# TEST 3 (through the service) — partial-box fill via occupancy
# --------------------------------------------------------------------------

def test_continue_mode_uses_live_occupancy(fake_repo):
    fake_repo.products = {f"A{i}": _prod(f"A{i}", f"A NEW {i:02d}", "TAB") for i in range(20)}
    fake_repo.occupancy = {"A075": 3, "A074": 7}
    result = service.preview_assignment(
        "t", "s", unit="TAB", mode="continue", assignment_type="standard_box",
        letter="A", product_codes=list(fake_repo.products), start_number=1,
    )
    boxes = {b["box"]: b["added"] for b in result["boxes"]}
    assert boxes == {"A075": 4, "A076": 7, "A077": 7, "A078": 2}


# --------------------------------------------------------------------------
# TEST 12 — a product not in this store cannot be assigned (tenant/store safe)
# --------------------------------------------------------------------------

def test_missing_product_is_rejected(fake_repo):
    fake_repo.products = {"A1": _prod("A1", "A ONE", "TAB")}
    with pytest.raises(HTTPException) as exc:
        service.preview_assignment(
            "t", "s", unit="TAB", mode="new_label", assignment_type="standard_box",
            letter="A", product_codes=["A1", "OTHER_TENANT_CODE"], start_number=1,
        )
    assert exc.value.status_code == 400
    assert "not found in this store" in exc.value.detail


# --------------------------------------------------------------------------
# commit writes exactly the planned assignments + old-location capture
# --------------------------------------------------------------------------

def test_commit_writes_plan_with_old_location(fake_repo):
    fake_repo.products = {
        "A1": _prod("A1", "A ALPHA", "TAB", loc="A075", stock=10),
        "A2": _prod("A2", "A BETA", "TAB", loc=None, stock=5),
    }
    fake_repo.occupancy = {"A075": 3}
    result = service.commit_assignment(
        "t", "s", unit="TAB", mode="continue", assignment_type="standard_box",
        letter="A", product_codes=["A1", "A2"], start_number=1, user_id="u1",
    )
    assert result["committed"] is True
    assert fake_repo.committed["user"] == "u1"
    rows = {r["product_code"]: r for r in fake_repo.committed["rows"]}
    # old_location is each product's pre-assignment effective location
    assert rows["A1"]["old_location"] == "A075"
    assert rows["A2"]["old_location"] is None
    # both land in the partial box A075 (3 occupied + 2 = 5)
    assert rows["A1"]["box"] == "A075" and rows["A2"]["box"] == "A075"


def test_unknown_unit_is_rejected(fake_repo):
    fake_repo.products = {"X1": _prod("X1", "X CREAM", "CREAM")}
    with pytest.raises(HTTPException) as exc:
        service.preview_assignment(
            "t", "s", unit="CREAM", mode="new_label", assignment_type="standard_box",
            letter="X", product_codes=["X1"], start_number=1,
        )
    assert "No automatic location rule" in exc.value.detail
