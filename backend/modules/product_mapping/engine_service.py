"""Product Mapping Engine — run orchestration.

Loads the two stores' products, the configurable normalization dictionary and
the Phase-1 supplier pairs, runs the pure ``matcher`` (Phases 1-6), applies a
RapidFuzz refinement for the fuzzy tier (Phase 7), and persists the run. All
business rules live in the pure modules; this layer is only I/O + logging.
"""

import logging
import uuid

from modules.product_mapping import matcher, repository, source_repository

logger = logging.getLogger("product_mapping.engine")


def run_mapping(tenant_id, source_store_id, target_store_id, actor=None):
    """Run the engine for a source→target store pair. Returns a summary with the
    new ``run_id`` and auto/pending/preserved counts."""
    if not tenant_id or not source_store_id or not target_store_id:
        raise ValueError("tenant_id, source_store_id and target_store_id are required")
    if source_store_id == target_store_id:
        raise ValueError("source and target store must differ")

    terms = repository.load_active_terms(tenant_id)
    source = source_repository.load_store_products(tenant_id, source_store_id)
    target = source_repository.load_store_products(tenant_id, target_store_id)
    if not target:
        raise ValueError("target store has no synced products")
    pairs = source_repository.load_supplier_pairs(tenant_id, source_store_id, target_store_id)

    decisions = matcher.match_products(source, target, pairs, terms)
    _refine_with_rapidfuzz(decisions)

    run_id = str(uuid.uuid4())
    summary = repository.save_run(tenant_id, run_id, source_store_id, target_store_id,
                                  decisions, actor)
    summary.update({
        "run_id": run_id,
        "source_count": len(source),
        "target_count": len(target),
        "supplier_pairs": len(pairs),
    })
    logger.info("mapping run %s tenant=%s %s->%s %s",
                run_id, tenant_id, source_store_id, target_store_id, summary)
    return summary


def _refine_with_rapidfuzz(decisions):
    """Phase 7: re-rank PENDING candidates by a stronger fuzzy string metric.

    RapidFuzz sharpens the ordering of borderline matches; the confidence stays
    below the deterministic AUTO bar so these always remain PENDING for review.
    Degrades gracefully (no-op) if rapidfuzz is not installed."""
    try:
        from rapidfuzz import fuzz
    except ImportError:  # pragma: no cover - dependency optional at runtime
        logger.warning("rapidfuzz not installed — skipping fuzzy refinement (Phase 7)")
        return

    for d in decisions:
        if d["status"] != "PENDING" or not d["candidates"]:
            continue
        src = d["source_normalized_name"] or ""
        for c in d["candidates"]:
            tgt = c.get("target_normalized_name") or ""
            c["fuzzy_score"] = round(fuzz.token_set_ratio(src, tgt), 2)
        d["candidates"].sort(
            key=lambda c: (c.get("fuzzy_score", 0.0), c["total_score"]), reverse=True)
        best = d["candidates"][0]
        d["target_product_code"] = best["target_product_code"]
        d["target_product_name"] = best["target_product_name"]
        d["match_method"] = "FUZZY"
        d["confidence"] = round(max(d["confidence"], best["total_score"]), 2)
