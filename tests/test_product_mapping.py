"""Product Mapping Engine — pure rule tests (DB-free).

Locks the hard-won rules from the NMA/NMC discount migration:
  * normalization keeps numeric strength, collapses punctuation/spacing;
  * the structured parser extracts brand/strength/unit/form/pack;
  * scoring weights + MRP-as-tie-breaker;
  * engine phases run in order, unmatched-only, never overwrite; and above all
    ProductCode is never a match key — the 214 collision stays PENDING.
No database connection is opened.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.product_mapping import scoring  # noqa: E402
from modules.product_mapping.matcher import match_products  # noqa: E402
from modules.product_mapping.medicine_parser import extract_medicine_attributes  # noqa: E402
from modules.product_mapping.normalization import (  # noqa: E402
    normalize_product_name,
    strip_dosage_terms,
)


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def test_normalize_collapses_punctuation_and_keeps_strength():
    assert normalize_product_name("DOLO-650 TAB") == "DOLO650TAB"
    assert normalize_product_name("DOLO 650 TAB") == "DOLO650TAB"
    # both spellings collapse to the same matching key
    assert normalize_product_name("DOLO-650 TAB") == normalize_product_name("DOLO 650 TAB")


def test_normalize_never_removes_numeric_strength():
    for s in ("650", "500", "250", "0.5", "12.5"):
        assert s.replace(".", "") in normalize_product_name(f"MED {s} TAB")


def test_strip_dosage_terms_removes_form_words_not_strength():
    assert strip_dosage_terms("DOLO 650 TAB", {"TAB"}) == "DOLO650"
    assert strip_dosage_terms("PARA 500 TABLET", {"TABLET"}) == "PARA500"


def test_normalize_handles_empty():
    assert normalize_product_name("") == ""
    assert normalize_product_name(None) == ""


# --------------------------------------------------------------------------
# Structured medicine parser
# --------------------------------------------------------------------------

def test_parser_full_example():
    a = extract_medicine_attributes("DOLO 650MG TAB 15'S")
    assert a["brand"] == "DOLO"
    assert a["strength"] == "650"
    assert a["unit"] == "MG"
    assert a["dosage_form"] == "TAB"
    assert a["pack_size"] == "15"


def test_parser_keeps_brand_qualifier():
    a = extract_medicine_attributes("GENPRAZ DSR TAB")
    assert a["brand"] == "GENPRAZ DSR"   # DSR is identity, not a form
    assert a["dosage_form"] == "TAB"
    assert a["strength"] is None


def test_parser_canonicalizes_form():
    assert extract_medicine_attributes("AMOX 250 CAPSULES")["dosage_form"] == "CAP"
    assert extract_medicine_attributes("ROSCILLIN 250 INJ")["dosage_form"] == "INJ"


def test_parser_decimal_strength():
    a = extract_medicine_attributes("FOLITRAX 0.5 INJ")
    assert a["strength"] == "0.5"


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def test_score_identical_is_high():
    src = {"normalized_name": "DOLO650TAB", "brand": "DOLO", "strength": "650",
           "dosage_form": "TAB", "mrp": 30}
    b = scoring.calculate_match_score(src, dict(src))
    assert b["total_score"] > 95


def test_mrp_only_breaks_ties_never_carries():
    src = {"normalized_name": "AAA", "brand": "AAA", "strength": "1",
           "dosage_form": "TAB", "mrp": 100}
    # totally different name/brand/strength/form, identical MRP -> tiny score
    cand = {"normalized_name": "ZZZ", "brand": "ZZZ", "strength": "9",
            "dosage_form": "INJ", "mrp": 100}
    b = scoring.calculate_match_score(src, cand)
    assert b["mrp_score"] == 5.0
    assert b["total_score"] <= scoring.WEIGHTS["mrp"] + 1  # MRP alone can't approve


def test_mrp_tie_breaker_between_close_names():
    src = {"normalized_name": "DOLO650", "brand": "DOLO", "strength": "650",
           "dosage_form": "TAB", "mrp": 30}
    near = {"normalized_name": "DOLO650", "brand": "DOLO", "strength": "650",
            "dosage_form": "TAB", "mrp": 31}
    far = {"normalized_name": "DOLO650", "brand": "DOLO", "strength": "650",
           "dosage_form": "TAB", "mrp": 300}
    assert (scoring.calculate_match_score(src, near)["total_score"]
            > scoring.calculate_match_score(src, far)["total_score"])


def test_classify_thresholds():
    assert scoring.classify(scoring.CONFIDENCE["NORMALIZED"]) == "AUTO"
    assert scoring.classify(scoring.CONFIDENCE["FUZZY"]) == "PENDING"


# --------------------------------------------------------------------------
# Engine ordering + the ProductCode-collision guarantee
# --------------------------------------------------------------------------

def _by_source(decisions):
    return {d["source_product_code"]: d for d in decisions}


def test_productcode_collision_never_auto_matches():
    """NMA 214 = GENPRAZ DSR TAB, NMC 214 = ROSCILLIN 250 INJ. Same code,
    different medicine — must NOT auto-match on the shared ProductCode."""
    source = [{"product_code": "214", "product_name": "GENPRAZ DSR TAB", "mrp": 50}]
    target = [{"product_code": "214", "product_name": "ROSCILLIN 250 INJ", "mrp": 80}]
    d = _by_source(match_products(source, target))["214"]
    assert d["status"] == "PENDING"
    assert d["match_method"] != "SUPPLIER"


def test_supplier_pair_auto_matches_across_different_codes():
    source = [{"product_code": "10", "product_name": "GENPRAZ DSR TAB", "mrp": 50}]
    target = [{"product_code": "999", "product_name": "GENPRAZ DSR TABLET", "mrp": 50}]
    d = _by_source(match_products(source, target, supplier_pairs=[("10", "999")]))["10"]
    assert d["status"] == "AUTO"
    assert d["match_method"] == "SUPPLIER"
    assert d["target_product_code"] == "999"


def test_exact_then_normalized_precedence():
    source = [
        {"product_code": "1", "product_name": "DOLO 650 TAB", "mrp": 30},   # exact
        {"product_code": "2", "product_name": "DOLO-650 TAB", "mrp": 30},   # normalized only
    ]
    target = [
        {"product_code": "A", "product_name": "DOLO 650 TAB", "mrp": 30},
    ]
    out = _by_source(match_products(source, target))
    assert out["1"]["match_method"] == "EXACT" and out["1"]["status"] == "AUTO"
    # target A is claimed by the exact match, so product 2 cannot re-use it
    assert out["2"]["status"] == "PENDING"


def test_normalized_auto_match():
    source = [{"product_code": "1", "product_name": "DOLO-650 TAB", "mrp": 30}]
    target = [{"product_code": "A", "product_name": "DOLO 650 TAB", "mrp": 30}]
    d = _by_source(match_products(source, target))["1"]
    assert d["match_method"] == "NORMALIZED"
    assert d["status"] == "AUTO"


def test_ambiguous_name_defers_to_review_with_candidates():
    source = [{"product_code": "1", "product_name": "DOLO 650 TAB", "mrp": 30}]
    target = [
        {"product_code": "A", "product_name": "DOLO 650 TAB", "mrp": 30},
        {"product_code": "B", "product_name": "DOLO 650 TAB", "mrp": 31},
    ]
    d = _by_source(match_products(source, target))["1"]
    assert d["status"] == "PENDING"        # two exact matches -> ambiguous
    assert len(d["candidates"]) >= 2


def test_pending_ranks_candidates_by_score():
    # Neither target clears a deterministic phase (different strength/core), so
    # the source falls through to candidate ranking — the closer one leads.
    source = [{"product_code": "1", "product_name": "DOLO 650 TAB", "mrp": 30}]
    target = [
        {"product_code": "A", "product_name": "DOLO 655 TAB", "mrp": 30},   # closer
        {"product_code": "B", "product_name": "PARA 500 SYP", "mrp": 30},   # far
    ]
    d = _by_source(match_products(source, target))["1"]
    assert d["status"] == "PENDING"
    assert d["candidates"][0]["target_product_code"] == "A"
    assert d["candidates"][0]["total_score"] >= d["candidates"][-1]["total_score"]
