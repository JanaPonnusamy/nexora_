"""Pure matching core for the Product Mapping Engine — DB-free, unit-tested.

``match_products`` is the heart of the engine: given the source store's products,
the target store's products and the known-good supplier pairs, it runs the seven
phases IN ORDER, each only over the still-unmatched source products, and never
overwrites an earlier successful match.

    Phase 1  SUPPLIER   -> 100  (existing SupplierProductMatch pairs)
    Phase 2  EXACT      ->  99  (exact name, case-insensitive)
    Phase 3  NORMALIZED ->  98  (normalized name key)
    Phase 4  STRUCTURED ->  96  (core key + equal strength)
    Phase 5  candidate search (shorter normalized name is a substring of the other)
    Phase 6  candidate ranking (weighted score)
    Phase 7  FUZZY / review  (best candidate -> PENDING; nothing -> PENDING/unmatched)

HARD RULE, enforced structurally: matching NEVER uses ProductCode equality.
Phase 1 uses *explicit* supplier pairs, not equal codes, so the NMA 214 /
NMC 214 collision (GENPRAZ vs ROSCILLIN) can never auto-match — it falls through
to PENDING review. There is no code path that maps on ProductCode alone.
"""

from modules.product_mapping import scoring
from modules.product_mapping.medicine_parser import extract_medicine_attributes
from modules.product_mapping.normalization import (
    DEFAULT_DOSAGE_TERMS,
    normalize_product_name,
    strip_dosage_terms,
)

MAX_CANDIDATES = 5
BLOCK_PREFIX = 4   # normalized-name prefix length used to bucket candidate search


def _enrich(row, dosage_terms):
    name = (row.get("product_name") or "").strip()
    attrs = extract_medicine_attributes(name)
    return {
        "product_code": str(row.get("product_code")),
        "product_name": name,
        "normalized_name": normalize_product_name(name),
        "core_key": strip_dosage_terms(name, dosage_terms),
        "brand": attrs["brand"],
        "strength": attrs["strength"],
        "unit": attrs["unit"],
        "dosage_form": attrs["dosage_form"],
        "pack_size": attrs["pack_size"],
        "mrp": row.get("mrp"),
    }


def _decision(src, target=None, method=None, phase=None, confidence=0.0,
              status="PENDING", candidates=None):
    return {
        "source_product_code": src["product_code"],
        "source_product_name": src["product_name"],
        "source_normalized_name": src["normalized_name"],
        "target_product_code": target["product_code"] if target else None,
        "target_product_name": target["product_name"] if target else None,
        "match_method": method,
        "match_phase": phase,
        "confidence": round(float(confidence), 2),
        "status": status,
        "brand": src["brand"],
        "strength": src["strength"],
        "unit": src["unit"],
        "dosage_form": src["dosage_form"],
        "pack_size": src["pack_size"],
        "mrp": src["mrp"],
        "candidates": candidates or [],
    }


def _contains(a, b):
    """True if the shorter of a/b is a substring of the longer (Phase-5 search)."""
    if not a or not b:
        return False
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return short in long


def _rank_candidates(src, targets):
    scored = []
    for t in targets:
        breakdown = scoring.calculate_match_score(src, t)
        scored.append((breakdown["total_score"], t, breakdown))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for total, t, breakdown in scored[:MAX_CANDIDATES]:
        out.append({
            "target_product_code": t["product_code"],
            "target_product_name": t["product_name"],
            "target_normalized_name": t["normalized_name"],
            "brand": t["brand"],
            "strength": t["strength"],
            "dosage_form": t["dosage_form"],
            "mrp": t["mrp"],
            "reason": _reason(breakdown),
            **breakdown,
        })
    return out


def _reason(breakdown):
    parts = []
    if breakdown["name_score"]:
        parts.append(f"name {breakdown['name_score']:.0f}")
    if breakdown["brand_score"]:
        parts.append(f"brand {breakdown['brand_score']:.0f}")
    if breakdown["strength_score"]:
        parts.append("strength match")
    if breakdown["form_score"]:
        parts.append("form match")
    if breakdown["mrp_score"]:
        parts.append(f"mrp {breakdown['mrp_score']:.1f}")
    return ", ".join(parts) or "weak similarity"


def match_products(source_rows, target_rows, supplier_pairs=None, dosage_terms=None):
    """Run all phases. Returns a list of decision dicts (one per source product).

    ``source_rows`` / ``target_rows``: dicts with ``product_code, product_name,
    mrp``. ``supplier_pairs``: iterable of ``(source_code, target_code)`` from
    SupplierProductMatch. ``dosage_terms``: configurable strip vocabulary.
    """
    terms = frozenset(t.upper() for t in (dosage_terms or DEFAULT_DOSAGE_TERMS))
    pairs = {(str(s), str(t)) for s, t in (supplier_pairs or [])}

    sources = [_enrich(r, terms) for r in source_rows]
    targets = [_enrich(r, terms) for r in target_rows]

    by_code = {t["product_code"]: t for t in targets}
    claimed = set()  # target codes already auto-assigned (one-to-one)
    decisions = []

    def take(t):
        claimed.add(t["product_code"])

    remaining = list(sources)

    # --- Phase 1: SUPPLIER (explicit pairs — never code equality) ---
    still = []
    for s in remaining:
        matched = None
        for (sc, tc) in pairs:
            if sc == s["product_code"] and tc in by_code and tc not in claimed:
                matched = by_code[tc]
                break
        if matched:
            take(matched)
            decisions.append(_decision(s, matched, "SUPPLIER", 1,
                                       scoring.CONFIDENCE["SUPPLIER"], "AUTO"))
        else:
            still.append(s)
    remaining = still

    # --- Phase 2: EXACT name (case-insensitive) ---
    exact_index = {}
    for t in targets:
        exact_index.setdefault(t["product_name"].upper(), []).append(t)
    remaining = _name_phase(remaining, exact_index,
                            lambda s: s["product_name"].upper(),
                            "EXACT", 2, claimed, take, decisions)

    # --- Phase 3: NORMALIZED name ---
    norm_index = {}
    for t in targets:
        norm_index.setdefault(t["normalized_name"], []).append(t)
    remaining = _name_phase(remaining, norm_index,
                            lambda s: s["normalized_name"],
                            "NORMALIZED", 3, claimed, take, decisions)

    # --- Phase 4: STRUCTURED (core key + equal strength) ---
    struct_index = {}
    for t in targets:
        struct_index.setdefault(t["core_key"], []).append(t)
    still = []
    for s in remaining:
        cands = [t for t in struct_index.get(s["core_key"], [])
                 if t["product_code"] not in claimed
                 and (s["strength"] or None) == (t["strength"] or None)]
        if len(cands) == 1:
            take(cands[0])
            decisions.append(_decision(s, cands[0], "STRUCTURED", 4,
                                       scoring.CONFIDENCE["STRUCTURED"], "AUTO"))
        else:
            still.append(s)
    remaining = still

    # --- Phases 5-7: candidate search + rank + fuzzy/review ---
    # Block by a short normalized-name prefix so each unmatched source is only
    # scored against a small, plausible bucket — never the whole target store
    # (that would be O(n²) on a 40k-product store). The prefix is short enough
    # that "DOLO650" and "DOLO650TABLET15S" share a block (Phase-5 substring).
    available = [t for t in targets if t["product_code"] not in claimed]
    block_index = {}
    for t in available:
        block_index.setdefault(t["normalized_name"][:BLOCK_PREFIX], []).append(t)

    for s in remaining:
        bucket = block_index.get(s["normalized_name"][:BLOCK_PREFIX], [])
        contained = [t for t in bucket if _contains(s["normalized_name"], t["normalized_name"])]
        ranked = _rank_candidates(s, contained or bucket)
        best = ranked[0] if ranked else None
        if best and best["total_score"] > 0:
            decisions.append(_decision(
                s, {"product_code": best["target_product_code"],
                    "product_name": best["target_product_name"]},
                "FUZZY", 7, best["total_score"], "PENDING", ranked))
        else:
            decisions.append(_decision(s, None, None, 7, 0.0, "PENDING", ranked))

    return decisions


def find_candidates(name, target_rows, dosage_terms=None, limit=MAX_CANDIDATES):
    """Ad-hoc ranked candidate search for a free-text ``name`` against a target
    store's products — the reusable FindCandidates() service, pure and DB-free."""
    terms = frozenset(t.upper() for t in (dosage_terms or DEFAULT_DOSAGE_TERMS))
    src = _enrich({"product_code": None, "product_name": name, "mrp": None}, terms)
    key = src["normalized_name"][:BLOCK_PREFIX]
    # bucket by the same prefix block used in the engine, so a free-text search
    # against a 40k-product store only scores a small plausible set
    bucket = [_enrich(r, terms) for r in target_rows
              if normalize_product_name(r.get("product_name") or "")[:BLOCK_PREFIX] == key]
    contained = [t for t in bucket if _contains(src["normalized_name"], t["normalized_name"])]
    ranked = _rank_candidates(src, contained or bucket)
    return ranked[:limit]


def _name_phase(remaining, index, key_fn, method, phase, claimed, take, decisions):
    """Shared exact/normalized phase: unique unclaimed hit -> AUTO, else defer."""
    still = []
    for s in remaining:
        cands = [t for t in index.get(key_fn(s), []) if t["product_code"] not in claimed]
        if len(cands) == 1:
            take(cands[0])
            decisions.append(_decision(s, cands[0], method, phase,
                                       scoring.CONFIDENCE[method], "AUTO"))
        else:
            still.append(s)  # zero or ambiguous -> later phase / review
    return still
