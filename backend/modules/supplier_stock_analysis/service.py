"""Business shaping for Supplier Stock Analysis."""

from concurrent.futures import ThreadPoolExecutor

from fastapi import HTTPException

from modules.supplier_stock_analysis import excel_import, repository


def list_suppliers(tenant_id, store_id=None, search=""):
    return {"suppliers": repository.list_suppliers(tenant_id, store_id, search)}


def list_supplier_products(tenant_id, supplier_code, store_id=None, search="", only_available=True):
    return {
        "items": repository.list_supplier_products(
            tenant_id, supplier_code, store_id, search, only_available
        )
    }


def match_for_supplier_stock(supplier_stock_id, tenant_id=None):
    row = repository.supplier_stock_row(supplier_stock_id, tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Supplier stock row not found")
    match = repository.exact_mapping(
        row["tenant_id"],
        row["store_id"],
        row["supplier_code"],
        row["supplier_product_code"],
    )
    product_code = (match or {}).get("product_code") or row.get("product_code")
    return {
        "supplier_stock": row,
        "match_status": "exact" if match else ("resolved" if product_code else "unmatched"),
        "exact_match": match,
        "product_code": product_code,
        "suggestions": [] if product_code else repository.suggestions(
            row["tenant_id"], row.get("supplier_product_name"), row.get("store_id")
        ),
    }


def product_dashboard(tenant_id, product_code, months=6):
    with ThreadPoolExecutor(max_workers=5) as pool:
        stock_future = pool.submit(repository.all_store_stock, tenant_id, product_code)
        movement_future = pool.submit(repository.monthly_movement_all_stores, tenant_id, product_code, months)
        batches_future = pool.submit(repository.batches_all_stores, tenant_id, product_code)
        purchases_future = pool.submit(repository.purchase_history_all_stores, tenant_id, product_code)
        sales_future = pool.submit(repository.sales_history_all_stores, tenant_id, product_code)

        stock = stock_future.result()
        movement = movement_future.result()
        batches = batches_future.result()
        purchases = purchases_future.result()
        sales = sales_future.result()

    return {
        "product_code": product_code,
        "all_store_stock": stock,
        "chart": [{"store_name": r.get("store_name"), "stock": r.get("total_stock") or 0} for r in stock],
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
        dashboard = product_dashboard(match["supplier_stock"]["tenant_id"], product_code, months)
    return {**match, "dashboard": dashboard}


def update_mapping(payload):
    repository.upsert_mapping(payload)
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
