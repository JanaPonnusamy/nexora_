"""Supplier Queue service (Sprint 2, Module 4).

Resolves the product for a working item and returns its ranked supplier queue
(top-N), plus supplier search and statistics. Ranking is done by the repository
(purchase frequency, last GRN) — this layer only orchestrates.
"""

from fastapi import HTTPException

from modules.procurement import supplier_repository as repo
from modules.procurement import workspace_repository as items_repo


def get_queue(tenant_id, order_item_id, limit=3):
    item = items_repo.get_item(tenant_id, order_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Working item not found")
    # Rank from real purchase history keyed by the store's ProductCode.
    suppliers = repo.top_suppliers(
        tenant_id, item.get("product_code"), item.get("store_id"), limit
    )
    return {
        "order_item_id": order_item_id,
        "product_id": item["product_id"],
        "product_code": item.get("product_code"),
        "suppliers": suppliers,
    }


def get_queue_bulk(tenant_id, refresh_id, limit=5):
    """Top-N supplier recommendations for every working item in a Refresh.

    Groups the flat ranked rows from the repository into one entry per order
    item so the Product Grid can render supplier icons for all rows at once.
    Read-only; reuses the same ranking as ``get_queue``.
    """
    rows = repo.top_suppliers_bulk(tenant_id, refresh_id, limit)
    by_item = {}
    for r in rows:
        oid = r["order_item_id"]
        entry = by_item.get(oid)
        if entry is None:
            entry = {
                "order_item_id": oid,
                "product_code": r.get("product_code"),
                "suppliers": [],
            }
            by_item[oid] = entry
        entry["suppliers"].append({
            "supplier_code": r.get("supplier_code"),
            "supplier_name": r.get("supplier_name"),
            "purchase_frequency": r.get("purchase_frequency"),
            "last_grn_date": r.get("last_grn_date"),
            "last_grn_no": r.get("last_grn_no"),
            "last_purchase_rate": r.get("last_purchase_rate"),
            "avg_lead_days": r.get("avg_lead_days"),
            "auto_assign": bool(r.get("auto_assign", True)),
            "min_products": r.get("min_products") or 2,
        })
    return {"items": list(by_item.values())}


def search(tenant_id, store_id, query, limit=20):
    return {"suppliers": repo.search_suppliers(tenant_id, store_id, query, limit)}


def products_for_supplier(tenant_id, refresh_id, supplier_code):
    """Order-item ids in the Refresh that this supplier has purchase history for
    (Supplier Purchasing mode filters the grid to these)."""
    return {"order_item_ids": repo.products_for_supplier(tenant_id, refresh_id, supplier_code)}


def stats(tenant_id, supplier_code, store_id=None):
    return repo.supplier_stats(tenant_id, supplier_code, store_id)


def list_settings(tenant_id, store_id):
    """Every supplier's Auto Assign settings for a store (auto_assign,
    min_products, export_rank). The frontend narrows this to suppliers
    actually relevant to the open refresh (present in its recommendations
    feed) — kept store-scoped (not refresh-scoped) here so ranks a buyer sets
    persist across refreshes."""
    return {"suppliers": repo.list_supplier_settings(tenant_id, store_id)}


def update_settings(tenant_id, store_id, supplier_code, auto_assign=None, min_products=None, export_rank=None):
    repo.update_supplier_settings(tenant_id, store_id, supplier_code, auto_assign, min_products, export_rank)
    return {"ok": True}
