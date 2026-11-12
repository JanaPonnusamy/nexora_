"""Quick Stock — lightweight, passcode-gated stock lookup across all of a
tenant's branches. No user session, no RBAC scoping: just the PIN check in
router.py. Reuses stock_availability's repository (same stock.usp_* SPs);
this module only adds its own grouping/shaping so it has no dependency on
stock_availability's JWT-scoped service layer.
"""

from __future__ import annotations

from repositories.tenant_repository import TenantRepository
from modules.stock_availability import repository


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


def search_products(tenant_id, query, only_stock):
    rows = repository.search_products(tenant_id, query or None, 1 if only_stock else 0)
    return _group_by_store(rows)


def product_core(tenant_id, store_id, product_code, months=3):
    return repository.get_product_core(tenant_id, store_id, product_code, months)
