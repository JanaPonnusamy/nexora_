"""Candidate scoring + confidence banding — pure, DB-free, unit-tested.

Weighted match score (spec weights):

    Normalized Name 40 | Brand 25 | Strength 20 | Dosage Form 10 | MRP 5

MRP is only ever a tie-breaker — never the primary key. Two candidates with
near-identical names are separated by how close their MRP is, but MRP alone can
never carry a match.

Confidence bands map an engine phase to a headline confidence, and
``classify`` decides AUTO vs PENDING. Deterministic phases (supplier / exact /
normalized / structured, >= AUTO_MIN) auto-accept; fuzzy matches (94-95) and
anything lower stay PENDING for human review — never auto-update a
low-confidence match.
"""

from difflib import SequenceMatcher

WEIGHTS = {"name": 40.0, "brand": 25.0, "strength": 20.0, "form": 10.0, "mrp": 5.0}

# Headline confidence per match method / phase.
CONFIDENCE = {
    "SUPPLIER": 100.0,    # phase 1 — existing SupplierProductMatch
    "EXACT": 99.0,        # phase 2 — exact name (case-insensitive)
    "NORMALIZED": 98.0,   # phase 3 — normalized name
    "STRUCTURED": 96.0,   # phase 4 — structured attribute match
    "FUZZY": 94.0,        # phase 7 — RapidFuzz
    "MANUAL": 100.0,      # human-approved
}

AUTO_MIN = 96.0   # >= this auto-accepts (deterministic phases only)
FUZZY_MIN = 94.0  # 94..96 -> PENDING review; below 94 -> PENDING (low)


def _ratio(a, b):
    a = (a or "").upper()
    b = (b or "").upper()
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _norm_strength(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v).upper()


def _mrp_closeness(a, b):
    """1.0 when MRPs match, decaying to 0 as they diverge; 0 if either missing."""
    try:
        a = float(a)
        b = float(b)
    except (TypeError, ValueError):
        return 0.0
    if a <= 0 or b <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(a - b) / max(a, b))


def calculate_match_score(source, candidate):
    """Weighted 0-100 score + per-signal breakdown for a source/candidate pair.

    Both are dicts with ``normalized_name, brand, strength, dosage_form, mrp``.
    Returns ``{name_score, brand_score, strength_score, form_score, mrp_score,
    total_score}`` — each already weighted.
    """
    name = _ratio(source.get("normalized_name"), candidate.get("normalized_name"))
    brand = _ratio(source.get("brand"), candidate.get("brand"))

    s_src, s_cand = _norm_strength(source.get("strength")), _norm_strength(candidate.get("strength"))
    strength = 1.0 if s_src is not None and s_src == s_cand else 0.0

    f_src, f_cand = source.get("dosage_form"), candidate.get("dosage_form")
    form = 1.0 if f_src and f_src == f_cand else 0.0

    mrp = _mrp_closeness(source.get("mrp"), candidate.get("mrp"))

    breakdown = {
        "name_score": round(name * WEIGHTS["name"], 2),
        "brand_score": round(brand * WEIGHTS["brand"], 2),
        "strength_score": round(strength * WEIGHTS["strength"], 2),
        "form_score": round(form * WEIGHTS["form"], 2),
        "mrp_score": round(mrp * WEIGHTS["mrp"], 2),
    }
    breakdown["total_score"] = round(sum(breakdown.values()), 2)
    return breakdown


def confidence_for(method):
    """Headline confidence for a match method (defaults to 0 if unknown)."""
    return CONFIDENCE.get((method or "").upper(), 0.0)


def classify(confidence):
    """AUTO if confidence clears the deterministic bar, else PENDING review."""
    return "AUTO" if confidence >= AUTO_MIN else "PENDING"
