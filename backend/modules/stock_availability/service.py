"""Business orchestration for the Stock Availability module.

The stored procedures return flat rows (one row per product/store). The search
screen groups those rows into one independent card per branch and derives the
summary tiles shown at the top of the reference UI. Detail panels pass straight
through to their procedures.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from dependencies.store_scope import assert_store_access, assert_tenant_access
from modules.stock_availability import repository


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
