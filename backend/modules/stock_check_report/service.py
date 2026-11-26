from modules.stock_check_report import repository


def search_sublocations(tenant_id, store_id, search_text):
    return repository.search_sublocations(tenant_id, store_id, (search_text or "").strip())


def list_suppliers(tenant_id, store_id):
    return repository.list_suppliers(tenant_id, store_id)


def list_units(tenant_id, store_id):
    return repository.list_units(tenant_id, store_id)


def _clean(value):
    if value is None:
        return None
    value = value.strip() if isinstance(value, str) else value
    return value or None


def get_stock_check_report(tenant_id, store_id, query):
    filters = {
        "sublocation_from": _clean(query.sublocation_from),
        "sublocation_to": _clean(query.sublocation_to),
        "product_code_from": query.product_code_from,
        "product_code_to": query.product_code_to,
        "product_name": _clean(query.product_name),
        "supplier_code": _clean(query.supplier_code),
        "unit_description": _clean(query.unit_description),
        "batch_code": _clean(query.batch_code),
        "expiry_from": _clean(query.expiry_from),
        "expiry_to": _clean(query.expiry_to),
        "min_stock": query.min_stock,
        "max_stock": query.max_stock,
        "include_zero_stock": bool(query.include_zero_stock),
        "include_negative_stock": bool(query.include_negative_stock),
    }
    rows = repository.get_stock_check_rows(tenant_id, store_id, filters)
    return {"rows": rows}
