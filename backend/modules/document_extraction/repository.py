"""Data access for the Document Extraction tables (dbo.doc_import and friends).

Raw pyodbc, parameterized. PKs are BIGINT IDENTITY (see sql/0001_...sql for
why — the platform's usual UNIQUEIDENTIFIER-PK convention was deliberately
overridden for this module's scale requirements). Every insert uses an
OUTPUT clause to get the new identity value back in the same round trip.
"""

import json
import uuid
from decimal import Decimal

from config.database import get_connection
from modules.procurement._dbutil import as_uid, rows_to_dicts as _rows_to_dicts


def _normalize(row: dict) -> dict:
    """JSON-safe a pyodbc result row: UUID -> str, Decimal -> float. Column
    values that are already JSON text (validation_json, ocr_json, ...) are
    left as strings here; callers that need the parsed form use the
    *_json helpers below."""
    out = {}
    for key, value in row.items():
        if isinstance(value, uuid.UUID):
            out[key] = str(value)
        elif isinstance(value, Decimal):
            out[key] = float(value)
        else:
            out[key] = value
    return out


def _rows(cur):
    return [_normalize(r) for r in _rows_to_dicts(cur)]


def _dumps(value):
    return json.dumps(value) if value is not None else None


def _loads(text):
    return json.loads(text) if text else None


# --------------------------------------------------------------------------
# doc_import
# --------------------------------------------------------------------------

def create_import(
    tenant_id, store_id, source_type, original_file_path,
    original_file_checksum, uploaded_by,
    is_duplicate=False, duplicate_of_import_id=None,
):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.doc_import (
                tenant_id, store_id, status, source_type, original_file_path,
                original_file_checksum, is_duplicate, duplicate_of_import_id,
                uploaded_by
            )
            OUTPUT INSERTED.import_id
            VALUES (?, ?, 'UPLOADED', ?, ?, ?, ?, ?, ?)
            """,
            (
                as_uid(tenant_id), as_uid(store_id), source_type,
                original_file_path, original_file_checksum,
                1 if is_duplicate else 0, duplicate_of_import_id,
                as_uid(uploaded_by),
            ),
        )
        import_id = cur.fetchone()[0]
        conn.commit()
        return import_id
    finally:
        conn.close()


def set_original_files(
    import_id, original_file_path, original_files_json,
    is_duplicate, duplicate_of_import_id, page_count=None,
):
    """One-time finalize of the upload: primary path, the full OriginalFiles
    page list (see json_contracts.OriginalFilesContract), and the duplicate
    flag/pointer resolved after the row already exists. Also flips
    is_upload_completed — upload is done once files are on disk and the page
    list is recorded, which is exactly what this call represents.

    `page_count` should be passed for image uploads (the file count IS the
    page count); leave it None for a single PDF, whose real page count is
    only known after Chunk 5 splits it."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.doc_import
            SET original_file_path = ?, original_files_json = ?,
                is_duplicate = ?, duplicate_of_import_id = ?,
                is_upload_completed = 1,
                page_count = COALESCE(?, page_count)
            WHERE import_id = ?
            """,
            (
                original_file_path, _dumps(original_files_json),
                1 if is_duplicate else 0, duplicate_of_import_id,
                page_count, import_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def find_duplicate_by_checksum(tenant_id, store_id, checksum, exclude_import_id=None):
    """Most recent non-deleted import with the same checksum for this
    store, or None. Used to flag (never block) a repeat upload.

    `exclude_import_id` must be passed as the just-created row's own id when
    called after that row has already been inserted (the checksum is
    written at INSERT time so the row would otherwise match itself)."""
    if not checksum:
        return None
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 import_id FROM dbo.doc_import
            WHERE is_deleted = 0 AND original_file_checksum = ?
              AND tenant_id = ? AND (store_id = ? OR (store_id IS NULL AND ? IS NULL))
              AND (? IS NULL OR import_id != ?)
            ORDER BY uploaded_at DESC
            """,
            (
                checksum, as_uid(tenant_id), as_uid(store_id), as_uid(store_id),
                exclude_import_id, exclude_import_id,
            ),
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def get_import(import_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM dbo.doc_import WHERE import_id = ?", (import_id,))
        rows = _rows(cur)
        if not rows:
            return None
        row = rows[0]
        for json_field in (
            "validation_json", "gst_slab_breakup_json",
            "original_files_json", "processed_files_json", "latest_export_json",
        ):
            row[json_field] = _loads(row.get(json_field))
        return row
    finally:
        conn.close()


def list_imports(
    tenant_id, store_id=None, status=None, supplier_name=None,
    invoice_number=None, date_from=None, date_to=None, has_errors=None,
    page=1, page_size=25,
):
    conditions = ["is_deleted = 0", "tenant_id = ?"]
    params = [as_uid(tenant_id)]

    if store_id:
        conditions.append("store_id = ?")
        params.append(as_uid(store_id))
    if status:
        conditions.append("status = ?")
        params.append(status)
    if supplier_name:
        conditions.append("supplier_name LIKE ?")
        params.append(f"%{supplier_name}%")
    if invoice_number:
        conditions.append("invoice_number LIKE ?")
        params.append(f"%{invoice_number}%")
    if date_from:
        conditions.append("invoice_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("invoice_date <= ?")
        params.append(date_to)
    if has_errors is True:
        conditions.append("validation_status IN ('WARNING', 'FAILED')")
    elif has_errors is False:
        conditions.append("validation_status = 'PASSED'")

    where_clause = " AND ".join(conditions)
    offset = (page - 1) * page_size

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM dbo.doc_import WHERE {where_clause}", params)
        total = cur.fetchone()[0]

        cur.execute(
            f"""
            SELECT import_id, import_guid, status, source_type, supplier_name,
                   matched_supplier_code, is_supplier_unknown, invoice_number,
                   invoice_date, net_amount, validation_status, is_duplicate,
                   uploaded_by, uploaded_at, reviewed_at, saved_at
            FROM dbo.doc_import
            WHERE {where_clause}
            ORDER BY uploaded_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            params + [offset, page_size],
        )
        return _rows(cur), total
    finally:
        conn.close()


_UPDATABLE_IMPORT_FIELDS = {
    "status", "failure_reason",
    "is_upload_completed", "is_image_processed", "is_ocr_completed",
    "is_header_extracted", "is_items_extracted", "is_reviewed", "is_exported",
    "processed_files_json", "preview_image_path", "page_count",
    "ocr_json", "ocr_confidence",
    "ocr_supplier_name", "supplier_name", "gst_number", "dl_number",
    "supplier_phone", "supplier_address", "matched_supplier_code",
    "supplier_match_method", "supplier_match_confidence", "is_supplier_unknown",
    "ocr_invoice_number", "invoice_number", "ocr_invoice_date", "invoice_date",
    "invoice_type", "order_number", "transport", "salesman", "credit_days",
    "gross_amount", "discount_amount", "scheme_discount", "cash_discount",
    "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "cess_amount",
    "round_off", "net_amount", "item_count", "total_quantity",
    "irn_number", "ack_number", "ack_date", "gst_slab_breakup_json",
    "validation_status", "validation_json", "latest_export_json",
    "reviewed_by", "reviewed_at", "saved_at",
}

# original_file_path/original_files_json/is_duplicate/duplicate_of_import_id
# are intentionally NOT here — they're a one-time write via
# set_original_files() at upload finalize, not a general PATCH target.
_JSON_IMPORT_FIELDS = {
    "validation_json", "gst_slab_breakup_json",
    "processed_files_json", "latest_export_json",
}


def update_import_fields(import_id, fields: dict):
    """Whitelisted dynamic UPDATE. `fields` keys must be in
    _UPDATABLE_IMPORT_FIELDS; anything else raises rather than silently
    no-op-ing (a typo'd field name should fail loudly, not vanish)."""
    if not fields:
        return
    unknown = set(fields) - _UPDATABLE_IMPORT_FIELDS
    if unknown:
        raise ValueError(f"Not updatable on doc_import: {sorted(unknown)}")

    set_clauses = []
    params = []
    for key, value in fields.items():
        set_clauses.append(f"{key} = ?")
        params.append(_dumps(value) if key in _JSON_IMPORT_FIELDS else value)
    set_clauses.append("updated_at = SYSUTCDATETIME()")
    params.append(import_id)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE dbo.doc_import SET {', '.join(set_clauses)} WHERE import_id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()


def soft_delete_import(import_id, deleted_by):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.doc_import
            SET is_deleted = 1, deleted_at = SYSUTCDATETIME(), deleted_by = ?
            WHERE import_id = ? AND is_deleted = 0
            """,
            (as_uid(deleted_by), import_id),
        )
        updated = cur.rowcount > 0
        conn.commit()
        return updated
    finally:
        conn.close()


# --------------------------------------------------------------------------
# doc_import_item
# --------------------------------------------------------------------------

def list_items(import_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM dbo.doc_import_item WHERE import_id = ? ORDER BY line_number",
            (import_id,),
        )
        return _rows(cur)
    finally:
        conn.close()


def get_item(item_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM dbo.doc_import_item WHERE item_id = ?", (item_id,))
        rows = _rows(cur)
        return rows[0] if rows else None
    finally:
        conn.close()


_UPDATABLE_ITEM_FIELDS = {
    "product_code", "product_guid", "normalized_product_name",
    "pack", "hsn_code", "batch_number", "expiry_raw", "expiry_date",
    "quantity", "free_quantity", "ptr", "purchase_rate", "mrp",
    "gst_percent", "discount_percent", "discount_amount", "amount",
    "confidence", "is_excluded",
}


def update_item_fields(item_id, fields: dict):
    if not fields:
        return
    unknown = set(fields) - _UPDATABLE_ITEM_FIELDS
    if unknown:
        raise ValueError(f"Not updatable on doc_import_item: {sorted(unknown)}")

    set_clauses = [f"{key} = ?" for key in fields]
    params = list(fields.values())
    set_clauses.append("updated_at = SYSUTCDATETIME()")
    params.append(item_id)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE dbo.doc_import_item SET {', '.join(set_clauses)} WHERE item_id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# doc_import_review — manual correction log
# --------------------------------------------------------------------------

def insert_review_entry(import_id, item_id, field_name, old_value, new_value, corrected_by):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.doc_import_review (
                tenant_id, import_id, item_id, field_name, old_value, new_value, corrected_by
            )
            OUTPUT INSERTED.review_id
            SELECT tenant_id, ?, ?, ?, ?, ?, ?
            FROM dbo.doc_import WHERE import_id = ?
            """,
            (
                import_id, item_id, field_name,
                None if old_value is None else str(old_value),
                None if new_value is None else str(new_value),
                as_uid(corrected_by), import_id,
            ),
        )
        review_id = cur.fetchone()[0]
        conn.commit()
        return review_id
    finally:
        conn.close()


def list_corrections(import_id, page=1, page_size=100):
    offset = (page - 1) * page_size
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM dbo.doc_import_review WHERE import_id = ?", (import_id,)
        )
        total = cur.fetchone()[0]
        cur.execute(
            """
            SELECT * FROM dbo.doc_import_review
            WHERE import_id = ?
            ORDER BY corrected_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            (import_id, offset, page_size),
        )
        return _rows(cur), total
    finally:
        conn.close()


# --------------------------------------------------------------------------
# doc_export_history
# --------------------------------------------------------------------------

def insert_export_history(export_batch_id, import_id, file_format, storage_path, row_count, exported_by):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.doc_export_history (
                tenant_id, export_batch_id, import_id, file_format,
                storage_path, row_count, exported_by
            )
            OUTPUT INSERTED.export_id
            SELECT tenant_id, ?, ?, ?, ?, ?, ?
            FROM dbo.doc_import WHERE import_id = ?
            """,
            (export_batch_id, import_id, file_format, storage_path, row_count,
             as_uid(exported_by), import_id),
        )
        export_id = cur.fetchone()[0]
        conn.commit()
        return export_id
    finally:
        conn.close()


def list_export_history(import_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM dbo.doc_export_history WHERE import_id = ? ORDER BY exported_at DESC",
            (import_id,),
        )
        return _rows(cur)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# doc_supplier_layout — column-mapping config (Settings page)
# --------------------------------------------------------------------------

def list_supplier_layouts(tenant_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM dbo.doc_supplier_layout WHERE tenant_id = ? AND is_active = 1 "
            "ORDER BY supplier_code",
            (as_uid(tenant_id),),
        )
        rows = _rows(cur)
        for row in rows:
            row["layout_json"] = _loads(row.get("layout_json"))
        return rows
    finally:
        conn.close()


def get_supplier_layout(tenant_id, supplier_code):
    """The active layout for a supplier, falling back to the tenant's global
    default (supplier_code IS NULL) when no supplier-specific one exists."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 * FROM dbo.doc_supplier_layout
            WHERE tenant_id = ? AND is_active = 1
              AND (supplier_code = ? OR supplier_code IS NULL)
            ORDER BY CASE WHEN supplier_code IS NULL THEN 1 ELSE 0 END
            """,
            (as_uid(tenant_id), supplier_code),
        )
        rows = _rows(cur)
        if not rows:
            return None
        row = rows[0]
        row["layout_json"] = _loads(row.get("layout_json"))
        return row
    finally:
        conn.close()


def upsert_supplier_layout(layout_id, tenant_id, supplier_code, layout_name, layout_json, actor):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if layout_id:
            cur.execute(
                """
                UPDATE dbo.doc_supplier_layout
                SET layout_name = ?, layout_json = ?, updated_at = SYSUTCDATETIME(), updated_by = ?
                WHERE layout_id = ? AND tenant_id = ?
                """,
                (layout_name, _dumps(layout_json), as_uid(actor), layout_id, as_uid(tenant_id)),
            )
            conn.commit()
            return layout_id
        cur.execute(
            """
            INSERT INTO dbo.doc_supplier_layout (
                tenant_id, supplier_code, layout_name, layout_json, created_by
            )
            OUTPUT INSERTED.layout_id
            VALUES (?, ?, ?, ?, ?)
            """,
            (as_uid(tenant_id), supplier_code, layout_name, _dumps(layout_json), as_uid(actor)),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    finally:
        conn.close()


# --------------------------------------------------------------------------
# doc_product_mapping — ProductCode resolution (wired in Chunk 9)
#
# This is the low-level DB half only (given an already-normalized key).
# The public pipeline interface — including the MASTER_PRODUCT check this
# function doesn't know about — is product_resolution.resolve_product();
# item_extract.py (Chunk 9) should call that, not this function directly.
# --------------------------------------------------------------------------

def resolve_product_code(tenant_id, supplier_code, ocr_product_name, normalized_product_name, normalized_product_key):
    """Look up an existing dbo.doc_product_mapping row by (supplier_code,
    normalized_product_key) (falling back to the global supplier_code IS
    NULL bucket); insert a new one if none exists. Returns (product_code,
    product_guid, source) where source is "EXISTING_MAPPING" or
    "NEW_MAPPING" (see product_resolution.py for the full 3-source contract,
    including "MASTER_PRODUCT" which this function does not handle).

    Stub for Chunk 3/4 — the normalization step that produces
    normalized_product_key belongs to item_extract.py (Chunk 9). Wiring the
    lookup/insert signature now so doc_product_mapping isn't dead schema."""
    raise NotImplementedError("Product resolution is implemented in Chunk 9 (Product Extraction)")
