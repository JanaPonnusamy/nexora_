"""Shelf Sorting & Excel Split.

Takes the existing export dataset for a whole Refresh, sorts it by shelf
category -> SubLocation -> ProductName (see export_document_service), and
splits it into consecutive .xlsx files of at most 16 products each — the exact
same Purchase Order layout the normal export produces, just reordered and cut
into pick-sized sheets. A single file is returned as-is; two or more are
bundled into one ZIP.

Reuses export_repository (to resolve the assignments) and
export_document_service (the one and only Excel engine) — no export logic is
duplicated here.
"""

import logging
import zipfile
from io import BytesIO

from fastapi import HTTPException

from config.database import get_connection
from modules.procurement import export_repository
from modules.procurement import export_document_service as docs

logger = logging.getLogger("procurement.shelf_sort")

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ZIP = "application/zip"
_MAX_PER_FILE = 16


def generate(tenant_id, refresh_id, store_name, columns=None, order_qty_header="Order Qty"):
    """Returns (content_bytes, filename, media_type, total_products, file_count).

    One product-file -> that .xlsx directly; multiple -> a .zip of them all.
    """
    conn = get_connection()
    try:
        assignments = export_repository.all_assignment_items(conn, tenant_id, refresh_id)
    finally:
        conn.close()

    items = [{"assignment_id": a["assignment_id"], "qty": a["assigned_qty"]} for a in assignments]
    if not items:
        raise HTTPException(status_code=400, detail="No products to sort for this order.")

    files, total = docs.build_sorted_split(
        tenant_id, items, columns or [], order_qty_header, store_name, _MAX_PER_FILE
    )

    logger.info("Shelf sort tenant=%s refresh=%s products=%s files=%s",
                tenant_id, refresh_id, total, len(files))

    if len(files) == 1:
        name, content = files[0]
        return content, name, _XLSX, total, 1

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files:
            zf.writestr(name, content)
    zip_name = f"{docs._safe_name(store_name)}_Sorted.zip"
    return buf.getvalue(), zip_name, _ZIP, total, len(files)
