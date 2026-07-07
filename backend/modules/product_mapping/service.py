"""Product Mapping — reusable public services.

The single import surface every other module (Discount Migration, Product Sync,
Procurement, Master-Data Merge, Store Migration, Supplier Mapping) uses. Thin
orchestration over the pure rule modules + repository; no business rules here.
"""

import logging

from modules.product_mapping import (
    engine_service,
    matcher,
    medicine_parser,
    normalization,
    repository,
    scoring,
    source_repository,
)

logger = logging.getLogger("product_mapping.service")


# --- pure reusable helpers (exposed for other modules) --------------------

def normalize_product_name(name):
    return normalization.normalize_product_name(name)


def extract_medicine_attributes(name):
    return medicine_parser.extract_medicine_attributes(name)


def calculate_match_score(source, candidate):
    return scoring.calculate_match_score(source, candidate)


def find_candidates(tenant_id, target_store_id, name, limit=5):
    """Ranked candidates in ``target_store`` for a free-text product name."""
    terms = repository.load_active_terms(tenant_id)
    targets = source_repository.load_store_products(tenant_id, target_store_id)
    return matcher.find_candidates(name, targets, terms, limit)


def search_mapped_product(tenant_id, source_store_id, source_product_code, target_store_id=None):
    return repository.search_mapped(tenant_id, source_store_id, source_product_code, target_store_id)


def search_products(tenant_id, store_id, query, limit=25):
    """Correct-Product picker: fast store-scoped lookup, each hit enriched with
    parsed medicine attributes (brand / strength / form / pack) for display."""
    rows = source_repository.search_store_products(tenant_id, store_id, query, limit)
    for r in rows:
        attrs = medicine_parser.extract_medicine_attributes(r.get("product_name"))
        r["brand"] = attrs.get("brand")
        r["strength"] = attrs.get("strength")
        r["unit_of_strength"] = attrs.get("unit")
        r["dosage_form"] = attrs.get("dosage_form")
        r["pack_size"] = attrs.get("pack_size")
    return rows


# --- engine + workflow ----------------------------------------------------

def run_mapping(tenant_id, source_store_id, target_store_id, actor=None):
    return engine_service.run_mapping(tenant_id, source_store_id, target_store_id, actor)


def list_mappings(tenant_id, **kwargs):
    return repository.list_mappings(tenant_id, **kwargs)


def get_mapping_detail(tenant_id, mapping_id):
    mapping = repository.get_mapping(tenant_id, mapping_id)
    if not mapping:
        return None
    mapping["candidates"] = repository.list_candidates(tenant_id, mapping_id)
    return mapping


def approve_mapping(tenant_id, mapping_id, actor, target_product_code=None, target_product_name=None):
    """Approve a mapping; when a candidate target is supplied this is a re-map
    (records MANUAL @ 100 confidence). Reused as ApproveMapping()."""
    updated = repository.set_status(
        tenant_id, mapping_id, "APPROVED", actor,
        target_product_code=target_product_code,
        target_product_name=target_product_name,
        method="MANUAL" if target_product_code else None,
        confidence=scoring.CONFIDENCE["MANUAL"] if target_product_code else None,
    )
    if updated:
        logger.info("mapping %s APPROVED by %s", mapping_id, actor)
    return updated


def reject_mapping(tenant_id, mapping_id, actor):
    updated = repository.set_status(tenant_id, mapping_id, "REJECTED", actor)
    if updated:
        logger.info("mapping %s REJECTED by %s", mapping_id, actor)
    return updated


def review_progress(tenant_id, source_store_id, target_store_id):
    return repository.review_progress(tenant_id, source_store_id, target_store_id)


def bulk_review(tenant_id, action, items, source_store_id, target_store_id,
                page=1, page_size=50, actor=None):
    """Approve/reject a whole selection in one transaction (Manual Review v2)."""
    result = repository.bulk_review(
        tenant_id, action, items, source_store_id, target_store_id,
        page=page, page_size=page_size, actor=actor)
    logger.info("bulk %s by %s: approved=%s rejected=%s skipped=%s remaining=%s",
                action, actor, result["approved"], result["rejected"],
                result["skipped"], result["remaining"])
    return result


# --- dashboard / statistics / audit --------------------------------------

def dashboard(tenant_id, source_store_id=None, target_store_id=None):
    counts = repository.status_counts(tenant_id, source_store_id, target_store_id)
    total = sum(counts.values())
    matched = counts["AUTO"] + counts["APPROVED"]
    return {
        "counts": counts,
        "total": total,
        "matched": matched,
        "match_rate": round(matched / total * 100, 1) if total else 0.0,
        "needs_review": counts["PENDING"],
    }


def statistics(tenant_id, source_store_id=None, target_store_id=None):
    return {
        "by_status": repository.status_counts(tenant_id, source_store_id, target_store_id),
        "by_method": repository.method_counts(tenant_id, source_store_id, target_store_id),
    }


def list_audit(tenant_id, mapping_id=None, page=1, page_size=100):
    return repository.list_audit(tenant_id, mapping_id, page, page_size)
