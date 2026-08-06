"""Business shaping for Supplier Stock Analysis."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from time import monotonic

from fastapi import HTTPException

from modules.product_mapping import service as mapping_service
from modules.supplier_stock_analysis import excel_import, repository


_CACHE_TTL_SECONDS = 90
_resolution_cache = {}
_stock_dashboard_cache = {}
_details_dashboard_cache = {}


def _cache_get(cache, key):
    entry = cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if expires_at <= monotonic():
        cache.pop(key, None)
        return None
    return deepcopy(value)


def _cache_set(cache, key, value):
    cache[key] = (monotonic() + _CACHE_TTL_SECONDS, deepcopy(value))
    return value


def list_suppliers(tenant_id, store_id=None, search=""):
    return {"suppliers": repository.list_suppliers(tenant_id, store_id, search)}


def list_supplier_products(tenant_id, supplier_code, store_id=None, search="", only_available=True):
    return {
        "items": repository.list_supplier_products(
            tenant_id, supplier_code, store_id, search, only_available
        )
    }


def supplier_analysis_report(tenant_id, supplier_code, store_id=None, only_available=False):
    rows = repository.supplier_analysis_report(tenant_id, supplier_code, store_id, only_available)
    summary = {
        "total_rows": len(rows),
        "already_mapped": 0,
        "stores_not_mapped": 0,
        "mapped_store_no_stock": 0,
        "home_store_no_stock_prediction": 0,
        "not_mapped_products": 0,
        "predicted_required_qty": 0,
    }
    for row in rows:
        bucket = row.get("analysis_bucket")
        if bucket in summary:
            summary[bucket] += 1
        summary["predicted_required_qty"] += int(row.get("predicted_required_qty") or 0)
    return {"rows": rows, "summary": summary}


def match_for_supplier_stock(supplier_stock_id, tenant_id=None):
    row = repository.supplier_stock_row(supplier_stock_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Supplier stock row not found")
    product_code = row.get("product_code")
    match = None
    match_status = "unmatched"

    # Fast path: imports + manual mapping writes already denormalize the mapped
    # ProductCode onto procurement.supplier_stock.product_code. Use that first
    # so opening each product row does not re-join SupplierProductMatch unless
    # this row truly has no resolved code yet.
    if product_code:
        match = repository.mapped_product(
            row["tenant_id"],
            row["store_id"],
            product_code,
        )
        match_status = "resolved"
    else:
        match = repository.exact_mapping(
            row["tenant_id"],
            row["store_id"],
            row["supplier_code"],
            row["supplier_product_code"],
        )
        product_code = (match or {}).get("product_code")
        match_status = "exact" if match else "unmatched"

    return {
        "supplier_stock": row,
        "match_status": match_status if product_code else "unmatched",
        "exact_match": match,
        "product_code": product_code,
        "suggestions": [] if product_code else mapping_service.find_candidates(
            row["tenant_id"], row.get("store_id"), row.get("supplier_product_name"), limit=10
        ),
    }


def _resolve_mapped_store_products(tenant_id, source_store_id, product_code, target_store_ids):
    """Per-target-store lookup via the shared product_mapping engine (one call
    per store), same call other modules use to resolve a cross-store mapping."""
    out = {}
    for target_store_id in target_store_ids:
        matches = mapping_service.search_mapped_product(
            tenant_id, source_store_id, product_code, target_store_id
        )
        if matches:
            best = matches[0]
            out[target_store_id] = {
                "product_code": best.get("target_product_code"),
                "product_name": best.get("target_product_name"),
            }
    return out


def _build_store_resolution(tenant_id, source_store_id, product_code):
    cache_key = (tenant_id, source_store_id, str(product_code))
    cached = _cache_get(_resolution_cache, cache_key)
    if cached is not None:
        return cached
    stores = repository.list_active_stores(tenant_id)
    target_store_ids = [store["store_id"] for store in stores if store["store_id"] != source_store_id]
    mapped = _resolve_mapped_store_products(
        tenant_id,
        source_store_id,
        product_code,
        target_store_ids,
    )
    pairs = []
    unresolved = []
    for store in stores:
        store_id = store["store_id"]
        if store_id == source_store_id:
            pairs.append({
                "store_id": store_id,
                "product_code": product_code,
                "product_name": None,
                "store_match_status": "source",
            })
            continue
        resolved = mapped.get(store_id)
        if resolved:
            pairs.append({
                "store_id": store_id,
                "product_code": resolved.get("product_code"),
                "product_name": resolved.get("product_name"),
                "store_match_status": "mapped",
            })
        else:
            unresolved.append({
                "store_id": store_id,
                "store_code": store.get("store_code"),
                "store_name": store.get("store_name"),
                "product_code": None,
                "product_name": None,
                "total_stock": 0,
                "sale_unit": None,
                "unit_description": None,
                "mrp": None,
                "ptr": None,
                "last_grn_date": None,
                "last_sale_date": None,
                "store_match_status": "unresolved",
            })
    return _cache_set(_resolution_cache, cache_key, (stores, pairs, unresolved))


def product_dashboard(tenant_id, source_store_id, product_code, months=6):
    stores, pairs, unresolved = _build_store_resolution(tenant_id, source_store_id, product_code)
    pair_meta = {row["store_id"]: row for row in pairs}
    with ThreadPoolExecutor(max_workers=5) as pool:
        stock_future = pool.submit(repository.all_store_stock, tenant_id, pairs)
        movement_future = pool.submit(repository.monthly_movement_all_stores, tenant_id, pairs, months)
        batches_future = pool.submit(repository.batches_all_stores, tenant_id, pairs)
        purchases_future = pool.submit(repository.purchase_history_all_stores, tenant_id, pairs)
        sales_future = pool.submit(repository.sales_history_all_stores, tenant_id, pairs)

        stock = stock_future.result()
        movement = movement_future.result()
        batches = batches_future.result()
        purchases = purchases_future.result()
        sales = sales_future.result()

    stock_by_store = {row["store_id"]: {**row} for row in stock}
    for store_id, meta in pair_meta.items():
        row = stock_by_store.get(store_id)
        if row:
            row["product_code"] = row.get("product_code") or meta.get("product_code")
            row["product_name"] = row.get("product_name") or meta.get("product_name")
            row["store_match_status"] = meta.get("store_match_status")
            stock_by_store[store_id] = row
    for row in unresolved:
        stock_by_store[row["store_id"]] = row

    ordered_stock = []
    seen = set()
    for store in stores:
        row = stock_by_store.get(store["store_id"])
        if not row:
            continue
        row["store_code"] = row.get("store_code") or store.get("store_code")
        row["store_name"] = row.get("store_name") or store.get("store_name")
        ordered_stock.append(row)
        seen.add(store["store_id"])
    for row in stock_by_store.values():
        if row["store_id"] not in seen:
            ordered_stock.append(row)

    return {
        "product_code": product_code,
        "all_store_stock": ordered_stock,
        "chart": [{"store_name": r.get("store_name"), "stock": r.get("total_stock") or 0} for r in ordered_stock],
        "movement": movement,
        "batches": batches,
        "purchases": purchases,
        "sales": sales,
    }


def supplier_stock_dashboard(supplier_stock_id, tenant_id=None, months=6):
    match = match_for_supplier_stock(supplier_stock_id, tenant_id)
    product_code = match.get("product_code")
    dashboard = None
    if product_code:
        dashboard = product_dashboard(
            match["supplier_stock"]["tenant_id"],
            match["supplier_stock"]["store_id"],
            product_code,
            months,
        )
    return {**match, "dashboard": dashboard}


def _stock_only_dashboard(tenant_id, source_store_id, product_code):
    cache_key = (tenant_id, source_store_id, str(product_code))
    cached = _cache_get(_stock_dashboard_cache, cache_key)
    if cached is not None:
        return cached
    stores, pairs, unresolved = _build_store_resolution(tenant_id, source_store_id, product_code)
    pair_meta = {row["store_id"]: row for row in pairs}
    stock = repository.all_store_stock(tenant_id, pairs)

    stock_by_store = {row["store_id"]: {**row} for row in stock}
    for store_id, meta in pair_meta.items():
        row = stock_by_store.get(store_id)
        if row:
            row["product_code"] = row.get("product_code") or meta.get("product_code")
            row["product_name"] = row.get("product_name") or meta.get("product_name")
            row["store_match_status"] = meta.get("store_match_status")
            stock_by_store[store_id] = row
    for row in unresolved:
        stock_by_store[row["store_id"]] = row

    ordered_stock = []
    seen = set()
    for store in stores:
        row = stock_by_store.get(store["store_id"])
        if not row:
            continue
        row["store_code"] = row.get("store_code") or store.get("store_code")
        row["store_name"] = row.get("store_name") or store.get("store_name")
        ordered_stock.append(row)
        seen.add(store["store_id"])
    for row in stock_by_store.values():
        if row["store_id"] not in seen:
            ordered_stock.append(row)

    result = {
        "product_code": product_code,
        "all_store_stock": ordered_stock,
        "chart": [{"store_name": r.get("store_name"), "stock": r.get("total_stock") or 0} for r in ordered_stock],
    }
    return _cache_set(_stock_dashboard_cache, cache_key, result)


def _details_only_dashboard(tenant_id, source_store_id, product_code, months=6):
    cache_key = (tenant_id, source_store_id, str(product_code), int(months))
    cached = _cache_get(_details_dashboard_cache, cache_key)
    if cached is not None:
        return cached
    _stores, pairs, _unresolved = _build_store_resolution(tenant_id, source_store_id, product_code)
    with ThreadPoolExecutor(max_workers=4) as pool:
        movement_future = pool.submit(repository.monthly_movement_all_stores, tenant_id, pairs, months)
        batches_future = pool.submit(repository.batches_all_stores, tenant_id, pairs)
        purchases_future = pool.submit(repository.purchase_history_all_stores, tenant_id, pairs)
        sales_future = pool.submit(repository.sales_history_all_stores, tenant_id, pairs)

        movement = movement_future.result()
        batches = batches_future.result()
        purchases = purchases_future.result()
        sales = sales_future.result()

    result = {
        "product_code": product_code,
        "movement": movement,
        "batches": batches,
        "purchases": purchases,
        "sales": sales,
    }
    return _cache_set(_details_dashboard_cache, cache_key, result)


def supplier_stock_dashboard_stock(supplier_stock_id, tenant_id=None):
    match = match_for_supplier_stock(supplier_stock_id, tenant_id)
    product_code = match.get("product_code")
    dashboard = None
    if product_code:
        dashboard = _stock_only_dashboard(
            match["supplier_stock"]["tenant_id"],
            match["supplier_stock"]["store_id"],
            product_code,
        )
    return {**match, "dashboard": dashboard}


def supplier_stock_dashboard_details(tenant_id, source_store_id, product_code, months=6):
    return _details_only_dashboard(tenant_id, source_store_id, product_code, months)


def family_for_supplier_stock(supplier_stock_id, tenant_id=None):
    """All plausible product variants for a supplier product (e.g. AMBRODIL,
    AMBRODIL D, AMBRODIL LS), each resolved across every active store -
    supports rendering one grid row per family member per store."""
    match = match_for_supplier_stock(supplier_stock_id, tenant_id)
    row = match["supplier_stock"]
    candidates = mapping_service.find_candidates(
        row["tenant_id"], row["store_id"], row.get("supplier_product_name"), limit=15
    )
    if match.get("product_code") and not any(
        c["target_product_code"] == str(match["product_code"]) for c in candidates
    ):
        exact = repository.mapped_product(row["tenant_id"], row["store_id"], match["product_code"])
        if exact:
            candidates.insert(0, {
                "target_product_code": exact["product_code"],
                "target_product_name": exact["product_name"],
                "total_score": 100,
            })

    stores = repository.list_active_stores(row["tenant_id"])
    target_store_ids = [s["store_id"] for s in stores if s["store_id"] != row["store_id"]]

    family = []
    for cand in candidates:
        product_code = cand["target_product_code"]
        mapped = _resolve_mapped_store_products(row["tenant_id"], row["store_id"], product_code, target_store_ids)
        per_store = [{
            "store_id": row["store_id"],
            "store_code": next((s.get("store_code") for s in stores if s["store_id"] == row["store_id"]), None),
            "store_name": next((s.get("store_name") for s in stores if s["store_id"] == row["store_id"]), None),
            "product_code": product_code,
            "product_name": cand.get("target_product_name"),
        }]
        for store in stores:
            if store["store_id"] == row["store_id"]:
                continue
            resolved = mapped.get(store["store_id"])
            per_store.append({
                "store_id": store["store_id"],
                "store_code": store.get("store_code"),
                "store_name": store.get("store_name"),
                "product_code": resolved.get("product_code") if resolved else None,
                "product_name": resolved.get("product_name") if resolved else None,
            })
        family.append({
            "product_code": product_code,
            "product_name": cand.get("target_product_name"),
            "confidence": cand.get("total_score"),
            "per_store": per_store,
        })

    return {"supplier_stock_id": supplier_stock_id, "family": family}


def global_search(tenant_id, query, store_id=None, limit=50):
    """Search Mode 2 (section 2): product code / product name, across one
    store or every active store when ``store_id`` is omitted."""
    query = (query or "").strip()
    if not query:
        return {"items": []}
    if store_id:
        results = mapping_service.search_products(tenant_id, store_id, query, limit)
        for r in results:
            r["store_id"] = store_id
        return {"items": results}

    stores = repository.list_active_stores(tenant_id)
    if not stores:
        return {"items": []}
    with ThreadPoolExecutor(max_workers=min(8, len(stores))) as pool:
        futures = {
            pool.submit(mapping_service.search_products, tenant_id, store["store_id"], query, limit): store
            for store in stores
        }
        items = []
        for future, store in futures.items():
            for r in future.result():
                r["store_id"] = store["store_id"]
                r["store_code"] = store.get("store_code")
                r["store_name"] = store.get("store_name")
                items.append(r)
    return {"items": items[:limit]}


def update_mapping(payload):
    repository.upsert_mapping(payload)
    tenant_id = payload["tenant_id"]
    store_id = payload["store_id"]
    source_keys = [key for key in _resolution_cache if key[0] == tenant_id and key[1] == store_id]
    for key in source_keys:
        _resolution_cache.pop(key, None)
        _stock_dashboard_cache.pop(key, None)
    detail_keys = [key for key in _details_dashboard_cache if key[0] == tenant_id and key[1] == store_id]
    for key in detail_keys:
        _details_dashboard_cache.pop(key, None)
    return {
        "success": True,
        "match": repository.exact_mapping(
            payload["tenant_id"],
            payload["store_id"],
            payload["supplier_code"],
            payload["supplier_product_code"],
        ),
    }


def preview_excel(file_bytes):
    return excel_import.preview(file_bytes)


def import_excel(tenant_id, store_id, supplier_code, file_bytes, mapping, imported_by=None):
    return excel_import.import_file(
        tenant_id, store_id, supplier_code, file_bytes, mapping, imported_by
    )
