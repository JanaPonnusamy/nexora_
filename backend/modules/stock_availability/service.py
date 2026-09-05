"""Business orchestration for the Stock Availability module.

The stored procedures return flat rows (one row per product/store). The search
screen groups those rows into one independent card per branch and derives the
summary tiles shown at the top of the reference UI. Detail panels pass straight
through to their procedures.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from dependencies.store_scope import assert_store_access, assert_tenant_access
from modules.product_mapping import matcher as mapping_matcher
from modules.product_mapping import repository as mapping_repository
from modules.product_mapping import source_repository as mapping_source_repository
from modules.product_mapping.medicine_parser import extract_medicine_attributes
from modules.stock_availability import repository

# Cross-store product-selection sync (Stock Availability grid) reuses the
# Product Mapping engine's pure matcher — see match_cross_store_selection()
# below — rather than re-implementing normalization/scoring here.
#
# The engine's own FUZZY phase (match_products Phase 7) exists to feed a human
# review queue: it surfaces the best candidate whenever ANY signal overlaps at
# all, however weak. Auto-selecting a row in another store with no human in
# the loop needs a stricter bar, so this module applies two extra guards on
# top of the engine's score before accepting a FUZZY result automatically:
#   * the weighted score must clear FUZZY_AUTO_MIN_SCORE
#   * parsed strength/dosage-form must not conflict (when both sides have one)
# The engine's STRUCTURED phase (core-key + equal strength) also has no
# dosage-form check of its own (e.g. "BRIV 100MG TAB" and "BRIV 100MG SYRUP"
# strip to the same core key), so the dosage-form guard is applied there too.
FUZZY_AUTO_MIN_SCORE = 60.0


def _conflicts(a, b):
    """True only when BOTH sides have a value and they differ — a missing
    attribute on either side is never treated as a conflict."""
    return bool(a) and bool(b) and a != b


def _decision_attrs(decision, targets):
    """(target_row, target_attrs, attr_conflict, brand_conflict) for one decision."""
    target_code = decision["target_product_code"]
    target_row = next((t for t in targets if t["product_code"] == target_code), None) if target_code else None
    target_attrs = extract_medicine_attributes(target_row["product_name"] or "") if target_row else {}
    source_attrs = {"strength": decision["strength"], "unit": decision["unit"], "dosage_form": decision["dosage_form"]}
    attr_conflict = (_conflicts(source_attrs["strength"], target_attrs.get("strength"))
                      or _conflicts(source_attrs["unit"], target_attrs.get("unit"))
                      or _conflicts(source_attrs["dosage_form"], target_attrs.get("dosage_form")))
    brand_conflict = _conflicts(decision["brand"], target_attrs.get("brand"))
    return target_row, target_attrs, attr_conflict, brand_conflict


def _match_one_store(tenant_id, source_row, terms, source_store_id, target_store_id):
    pairs = mapping_source_repository.load_supplier_pairs(tenant_id, source_store_id, target_store_id)
    targets = mapping_source_repository.load_store_products(tenant_id, target_store_id)
    decision = mapping_matcher.match_products([source_row], targets, supplier_pairs=pairs, dosage_terms=terms)[0]

    no_match = {"store_id": target_store_id, "match_type": "NO_MATCH", "score": 0.0, "product": None}
    method = decision["match_method"]
    target_row, target_attrs, attr_conflict, brand_conflict = _decision_attrs(decision, targets)

    if method == "SUPPLIER" and (attr_conflict or brand_conflict):
        # SupplierProductMatch pairs are curated for the Product Mapping
        # review workflow, not guaranteed correct for *auto*-selecting a row
        # here with no human in the loop — a stale or wrong pairing (e.g. two
        # unrelated products that happen to share a (SupplierCode,
        # SupplierProductCode) key in one store's data) would otherwise be
        # trusted at 100% confidence with zero sanity check. Phase 1 claims
        # the whole source row on a SUPPLIER hit, so EXACT/NORMALIZED/
        # STRUCTURED/FUZZY never got a chance to run for it — re-match with
        # that pairing excluded so a real equivalent already sitting in this
        # store's own catalog can still be found via the later phases.
        decision = mapping_matcher.match_products([source_row], targets, supplier_pairs=[], dosage_terms=terms)[0]
        method = decision["match_method"]
        target_row, target_attrs, attr_conflict, brand_conflict = _decision_attrs(decision, targets)

    if method == "SUPPLIER":
        match_type = "EXACT_SUPPLIER_MATCH"
    elif method in ("EXACT", "NORMALIZED"):
        match_type = "EXACT_NORMALIZED_NAME"
    elif method == "STRUCTURED":
        if attr_conflict:
            return no_match
        match_type = "STRONG_ATTRIBUTE_MATCH"
    elif method == "FUZZY":
        best = decision["candidates"][0] if decision["candidates"] else None
        # FUZZY is similarity-scored, not exact — equal strength/unit/form is not
        # enough on its own: two DIFFERENT brand families sharing a strength/form
        # (e.g. "BRIV 100MG TAB" vs "BRIVATOP 100MG TAB", a distinct product that
        # merely starts with the same letters) can otherwise clear the score
        # threshold on name-similarity + matching attributes alone. Require the
        # parsed brand to match too (when both sides have one) before auto-
        # selecting a fuzzy candidate — SUPPLIER/EXACT/NORMALIZED/STRUCTURED are
        # unaffected since each already pins the brand via an exact key/name.
        if (not best or best["total_score"] < FUZZY_AUTO_MIN_SCORE or attr_conflict
                or _conflicts(decision["brand"], best.get("brand"))):
            return {**no_match, "score": round(best["total_score"], 2) if best else 0.0}
        match_type = "RELEVANT_FUZZY_MATCH"
    else:
        return no_match

    return {
        "store_id": target_store_id,
        "match_type": match_type,
        "score": decision["confidence"],
        "product": {
            "product_code": decision["target_product_code"],
            "product_name": decision["target_product_name"],
            "mrp": target_row["mrp"] if target_row else None,
        },
    }


def match_cross_store_selection(user, tenant_id, source_store_id, source_product_code,
                                 source_product_name, target_store_ids):
    """For a product selected in one store, resolve its equivalent product in
    each of ``target_store_ids`` via the Product Mapping matching hierarchy
    (SupplierProductMatch -> normalized name -> structured attributes ->
    relevance-scored fuzzy candidate). Stores with no reliable match come back
    with ``match_type: NO_MATCH`` / ``product: null`` so the caller leaves that
    store's selection unchanged, never fabricating an equivalent."""
    assert_tenant_access(user, tenant_id)

    targets = [str(t) for t in (target_store_ids or []) if str(t) != str(source_store_id)]
    if not source_product_name or not targets:
        return {"results": []}

    terms = mapping_repository.load_active_terms(tenant_id)
    source_row = {
        "product_code": str(source_product_code),
        "product_name": source_product_name,
        "mrp": None,
    }

    results = []
    workers = min(8, len(targets))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_match_one_store, tenant_id, source_row, terms, source_store_id, tid): tid
            for tid in targets
        }
        for future in as_completed(futures):
            results.append(future.result())

    return {"results": results}


def _to_number(value):
    if value is None:
        return 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _group_by_store(rows):
    """Collapse flat product rows into per-branch cards + summary tiles."""
    stores = {}
    order = []
    for row in rows:
        store_id = str(row.get("store_id")) if row.get("store_id") is not None else ""
        if store_id not in stores:
            stores[store_id] = {
                "store_id": store_id,
                "store_code": row.get("store_code"),
                "store_name": row.get("store_name"),
                "total_stock": 0,
                "matching_count": 0,
                "products": [],
            }
            order.append(store_id)
        bucket = stores[store_id]
        stock = _to_number(row.get("stock"))
        bucket["products"].append(
            {
                "product_code": row.get("product_code"),
                "product_name": row.get("product_name"),
                "sale_unit": row.get("sale_unit"),
                "stock": stock,
                "mrp": _to_number(row.get("mrp")),
                "batch_no": row.get("batch_no"),
            }
        )
        bucket["total_stock"] += stock
        bucket["matching_count"] += 1

    cards = [stores[sid] for sid in order]
    total_stock_all = sum(card["total_stock"] for card in cards)
    stores_with_stock = sum(1 for card in cards if card["total_stock"] > 0)

    return {
        "stores": cards,
        "summary": {
            "total_stores": len(cards),
            "total_products_found": len(rows),
            "stores_with_stock": stores_with_stock,
            "total_stock_all_stores": total_stock_all,
        },
    }


def search_products(user, tenant_id, query, only_stock):
    assert_tenant_access(user, tenant_id)
    rows = repository.search_products(tenant_id, query or None, 1 if only_stock else 0)
    return _group_by_store(rows)


def search_batches(user, tenant_id, batch_no, mrp, product_name):
    assert_tenant_access(user, tenant_id)
    rows = repository.search_batches(
        tenant_id,
        batch_no or None,
        mrp if mrp not in ("", None) else None,
        product_name or None,
    )
    return _group_by_store(rows)


def product_details(user, tenant_id, store_id, product_code):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_product_details(tenant_id, store_id, product_code)


def product_core(user, tenant_id, store_id, product_code, months=3):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_product_core(tenant_id, store_id, product_code, months)


def product_core_bulk(user, tenant_id, items, months=3):
    assert_tenant_access(user, tenant_id)
    unique_items = []
    seen = set()
    for item in items or []:
        store_id = str(item.get("store_id") or "").strip()
        product_code = str(item.get("product_code") or "").strip()
        if not store_id or not product_code:
            continue
        key = (store_id, product_code)
        if key in seen:
            continue
        seen.add(key)
        unique_items.append({"store_id": store_id, "product_code": product_code})

    def _load_one(item):
        core = repository.get_product_core(tenant_id, item["store_id"], item["product_code"], months)
        # NOTE: the latest bill's line items are intentionally NOT fetched here.
        # get_bill_items is the slowest per-store query (200-700ms against the 3M
        # row sync.ProductSaleInformation), and nothing consumes this eager copy:
        # the bill drawer (BillDetailCard) fetches its own items on click via
        # /products/bill-items. Fetching it for every store on every search was
        # pure dead weight that dominated the multi-store load time. Keep the
        # keys (empty) so the response shape stays stable for the client.
        return {
            "store_id": item["store_id"],
            "product_code": item["product_code"],
            "batches": core.get("batches") or [],
            "purchases": core.get("purchases") or [],
            "sales": core.get("sales") or [],
            "movement": core.get("movement") or [],
            "billItems": [],
            "activeBillNo": None,
        }

    if not unique_items:
        return {"items": []}

    workers = min(8, len(unique_items))
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_load_one, item) for item in unique_items]
        for future in as_completed(futures):
            results.append(future.result())

    return {"items": results}


def batch_details(user, tenant_id, store_id, product_code):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_batch_details(tenant_id, store_id, product_code)


def batch_detail(user, tenant_id, store_id, product_code, batch_code):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_batch_detail(tenant_id, store_id, product_code, batch_code)


def purchase_history(user, tenant_id, store_id, product_code):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_purchase_history(tenant_id, store_id, product_code)


def sales_history(user, tenant_id, store_id, product_code):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_sales_history(tenant_id, store_id, product_code)


def bill_items(user, tenant_id, store_id, bill_no, bill_date):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_bill_items(tenant_id, store_id, bill_no, bill_date)


def monthly_movement(user, tenant_id, store_id, product_code, months=4):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_monthly_movement(tenant_id, store_id, product_code, months)


# ----- Bill Drawer (Purchase Manager detail panel) ------------------------

def purchase_bill(user, tenant_id, store_id, grn_no, grn_date):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_purchase_bill(tenant_id, store_id, grn_no, grn_date or None)


def sales_bill(user, tenant_id, store_id, bill_no, bill_date):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_sales_bill(tenant_id, store_id, bill_no, bill_date or None)


def set_sales_bill_line_ignore(
    user,
    tenant_id,
    store_id,
    bill_no,
    bill_date,
    product_code,
    batch,
    dont_consider_in_order,
):
    assert_store_access(user, tenant_id, store_id)
    updated = repository.set_sales_bill_line_ignore(
        tenant_id,
        store_id,
        bill_no,
        bill_date,
        product_code,
        batch,
        dont_consider_in_order,
    )
    return {
        "updated": updated,
        "dont_consider_in_order": bool(dont_consider_in_order),
    }


def product_availability(user, tenant_id, store_id, product_code):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_product_availability(tenant_id, store_id, product_code)


def customer_history(user, tenant_id, store_id, customer_code):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_customer_history(tenant_id, store_id, customer_code)


def repeat_purchase(user, tenant_id, store_id, product_code):
    assert_store_access(user, tenant_id, store_id)
    return repository.get_repeat_purchase(tenant_id, store_id, product_code)
