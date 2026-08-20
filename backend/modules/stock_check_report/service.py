from modules.stock_check_report import repository


def search_sublocations(tenant_id, store_id, search_text):
    return repository.search_sublocations(tenant_id, store_id, (search_text or "").strip())


def get_stock_check_report(tenant_id, store_id, sublocation_from, sublocation_to):
    rows = repository.get_stock_check_rows(
        tenant_id,
        store_id,
        (sublocation_from or "").strip(),
        (sublocation_to or "").strip(),
    )
    return {"rows": rows}
