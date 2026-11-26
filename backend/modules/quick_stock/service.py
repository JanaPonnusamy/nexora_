"""Quick Stock — lightweight, passcode-gated stock lookup across all of a
tenant's branches. No user session, no RBAC scoping: just the PIN check in
router.py. Reuses stock_availability's repository (same stock.usp_* SPs);
this module only adds its own grouping/shaping so it has no dependency on
stock_availability's JWT-scoped service layer.
"""

from __future__ import annotations

from config.database import get_connection
from repositories.tenant_repository import TenantRepository
from modules.stock_availability import repository
from modules.stock_availability import service as stock_availability_service


def _to_number(value):
    if value is None:
        return 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def list_tenants():
    rows = TenantRepository().get_all()
    return [
        {"tenant_id": str(r[0]), "tenant_name": r[3]}
        for r in rows
        if r[5]  # is_active
    ]


def _group_by_store(rows):
    stores = {}
    order = []
    for row in rows:
        store_id = str(row.get("store_id")) if row.get("store_id") is not None else ""
        if store_id not in stores:
            stores[store_id] = {
                "store_id": store_id,
                "store_code": row.get("store_code"),
                "store_name": row.get("store_name"),
                "products": [],
            }
            order.append(store_id)
        stores[store_id]["products"].append(
            {
                "product_code": row.get("product_code"),
                "product_name": row.get("product_name"),
                "sale_unit": row.get("sale_unit"),
                "stock": _to_number(row.get("stock")),
                "mrp": _to_number(row.get("mrp")),
            }
        )
    return {"stores": [stores[sid] for sid in order]}


def list_stores(tenant_id):
    """Store shells only (no products) -- lets the page render every branch's
    fixed-height frame immediately on open, before any search is typed."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT store_id, store_code, store_name FROM dbo.stores "
            "WHERE tenant_id = ? AND is_active = 1 ORDER BY store_order, store_code",
            tenant_id,
        )
        rows = cur.fetchall()
    finally:
        conn.close()
    return [
        {"store_id": str(r[0]), "store_code": r[1], "store_name": r[2]}
        for r in rows
    ]


def search_products(tenant_id, query, only_stock):
    rows = repository.search_products(tenant_id, query or None, 1 if only_stock else 0)
    return _group_by_store(rows)


def product_core(tenant_id, store_id, product_code, months=3):
    return repository.get_product_core(tenant_id, store_id, product_code, months)


def batch_details(tenant_id, store_id, product_code):
    return repository.get_batch_details(tenant_id, store_id, product_code)


def monthly_movement(tenant_id, store_id, product_code, months=4):
    return repository.get_monthly_movement(tenant_id, store_id, product_code, months)


def purchase_history(tenant_id, store_id, product_code):
    return repository.get_purchase_history(tenant_id, store_id, product_code)


def sales_history(tenant_id, store_id, product_code):
    return repository.get_sales_history(tenant_id, store_id, product_code)


def product_core_bulk(tenant_id, items, months=3):
    """Parallel per-store core loading for the all-stores detail view --
    without this, the page issued one HTTP request per store, each opening
    its own DB connection and running the same heavy query concurrently;
    under contention only the first 1-2 stores would finish, leaving the
    rest stuck on "Loading..." indefinitely. `user=None` passes
    stock_availability's unrestricted-scope check (see cross_store_match
    above for the same pattern)."""
    return stock_availability_service.product_core_bulk(None, tenant_id, items, months)


def product_core_bulk_split(tenant_id, items, months, mode):
    """Sales/Purchase toggle, every store in one request -- fetches ONLY the
    active mode's transactions (plus the mode-independent batches/movement
    the chart always needs), never both. `user=None` for the same reason as
    product_core_bulk above."""
    return stock_availability_service.product_core_bulk_split(None, tenant_id, items, months, mode)


def bill_items(tenant_id, store_id, bill_no, bill_date):
    return repository.get_bill_items(tenant_id, store_id, bill_no, bill_date)


def purchase_bill(tenant_id, store_id, grn_no, grn_date):
    return repository.get_purchase_bill(tenant_id, store_id, grn_no, grn_date)


def cross_store_match(tenant_id, source_store_id, source_product_code, source_product_name, target_store_ids):
    """Resolve the equivalent product in each target store via the real
    Product Mapping matcher (same engine the full Stock Availability page
    uses) -- NOT a naive exact product_name match, which silently drops
    stores whose product name differs by even one space/word from the
    source. `user=None` passes stock_availability's own unrestricted-scope
    check (see dependencies.store_scope.has_unrestricted_scope)."""
    return stock_availability_service.match_cross_store_selection(
        None, tenant_id, source_store_id, source_product_code, source_product_name, target_store_ids,
    )
