"""Business orchestration for the Stock Availability module.

The stored procedures return flat rows (one row per product/store). The search
screen groups those rows into one independent card per branch and derives the
summary tiles shown at the top of the reference UI. Detail panels pass straight
through to their procedures.
"""

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


def search_products(tenant_id, query, only_stock):
    rows = repository.search_products(tenant_id, query or None, 1 if only_stock else 0)
    return _group_by_store(rows)


def search_batches(tenant_id, batch_no, mrp, product_name):
    rows = repository.search_batches(
        tenant_id,
        batch_no or None,
        mrp if mrp not in ("", None) else None,
        product_name or None,
    )
    return _group_by_store(rows)


def product_details(tenant_id, store_id, product_code):
    return repository.get_product_details(tenant_id, store_id, product_code)


def product_core(tenant_id, store_id, product_code, months=3):
    return repository.get_product_core(tenant_id, store_id, product_code, months)


def batch_details(tenant_id, store_id, product_code):
    return repository.get_batch_details(tenant_id, store_id, product_code)


def purchase_history(tenant_id, store_id, product_code):
    return repository.get_purchase_history(tenant_id, store_id, product_code)


def sales_history(tenant_id, store_id, product_code):
    return repository.get_sales_history(tenant_id, store_id, product_code)


def bill_items(tenant_id, store_id, bill_no, bill_date):
    return repository.get_bill_items(tenant_id, store_id, bill_no, bill_date)


def monthly_movement(tenant_id, store_id, product_code, months=4):
    return repository.get_monthly_movement(tenant_id, store_id, product_code, months)


# ----- Bill Drawer (Purchase Manager detail panel) ------------------------

def purchase_bill(tenant_id, store_id, grn_no, grn_date):
    return repository.get_purchase_bill(tenant_id, store_id, grn_no, grn_date or None)


def sales_bill(tenant_id, store_id, bill_no, bill_date):
    return repository.get_sales_bill(tenant_id, store_id, bill_no, bill_date or None)


def product_availability(tenant_id, store_id, product_code):
    return repository.get_product_availability(tenant_id, store_id, product_code)


def customer_history(tenant_id, store_id, customer_code):
    return repository.get_customer_history(tenant_id, store_id, customer_code)


def repeat_purchase(tenant_id, store_id, product_code):
    return repository.get_repeat_purchase(tenant_id, store_id, product_code)
