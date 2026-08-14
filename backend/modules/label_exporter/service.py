from modules.label_exporter import repository


def search_products(
    tenant_id,
    store_id,
    q,
    starts_with,
    unit_description,
    box_number,
    stock_filter,
    only_null_sublocation,
    only_sale_unit_gt_one,
):
    starts_with = (starts_with or "").strip()
    stock_filter = (stock_filter or "all").strip() or "all"
    return {
        **repository.search_products(
            tenant_id,
            store_id,
            (q or "").strip(),
            starts_with,
            (unit_description or "").strip(),
            (box_number or "").strip(),
            stock_filter,
            bool(only_null_sublocation),
            bool(only_sale_unit_gt_one),
        ),
        "unit_descriptions": repository.get_unit_descriptions(tenant_id, store_id, starts_with),
    }


def search_boxes(tenant_id, store_id, q, starts_with):
    return {
        "boxes": repository.search_boxes(
            tenant_id,
            store_id,
            (q or "").strip(),
            (starts_with or "").strip(),
        )
    }


def get_box_products(tenant_id, store_id, box_number):
    return {"rows": repository.get_box_products(tenant_id, store_id, (box_number or "").strip())}


def get_product_batches(tenant_id, store_id, product_code):
    return {"rows": repository.get_product_batches(tenant_id, store_id, (product_code or "").strip())}
