"""Supplier Live Stock service (Sprint 2 — Workspace Completion).

Thin read-only orchestration over supplier_stock_repository. No business logic.
"""

from config.database import get_connection
from modules.procurement import supplier_stock_repository as repo
from modules.procurement import reconciliation_repository
from modules.procurement import supplier_stock_import as imp


def get_mapping(tenant_id, store_id, supplier_code):
    """Saved Excel header map for a supplier+store + the canonical targets."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT supplier_column_name, column_name FROM procurement.supplier_excel_mapping "
            "WHERE tenant_id = ? AND store_id = ? AND supplier_code = ? AND is_active = 1",
            (tenant_id, store_id, supplier_code),
        )
        mapping = {r[0]: r[1] for r in cur.fetchall()}
        return {
            "mapping": mapping,
            "targets": [{"value": v, "label": lbl, "mandatory": m}
                        for v, lbl, m in imp.CANONICAL_TARGETS],
        }
    finally:
        conn.close()


def preview_import(tenant_id, store_id, supplier_code, file_bytes, filename):
    existing = {k.lower(): v for k, v in get_mapping(tenant_id, store_id, supplier_code)["mapping"].items()}
    return imp.preview_excel(file_bytes, filename, existing)


def run_import(tenant_id, store_id, supplier_code, file_bytes, filename, mapping, created_by=None):
    return imp.import_excel(tenant_id, store_id, supplier_code, file_bytes,
                            filename, mapping, created_by)


def list_supplier_stock(tenant_id, refresh_id, supplier_code, search=None, only_available=True):
    refresh = reconciliation_repository.get_refresh(tenant_id, refresh_id)
    if not refresh:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Refresh not found")
    # Scope live stock to the refresh's store (keeps the match join cheap and
    # avoids mixing other branches' stock for the same supplier).
    items = repo.get_supplier_stock(
        tenant_id, refresh_id, supplier_code,
        store_id=refresh.get("store_id"), search=search, only_available=only_available,
    )
    return {"items": items}


def products_with_offers(tenant_id, refresh_id):
    """Product codes in this refresh's VPL that carry an offer — free qty or a
    discount % on the product's last purchase (sync.PurchaseTrans), or a live
    supplier scheme — scoped to this refresh's store. "Has Offer" filter
    (Review All / Supplier Purchasing)."""
    refresh = reconciliation_repository.get_refresh(tenant_id, refresh_id)
    if not refresh:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Refresh not found")
    codes = repo.products_with_offers(tenant_id, refresh_id, store_id=refresh.get("store_id"))
    return {"product_codes": codes}
