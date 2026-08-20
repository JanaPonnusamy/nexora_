"""Chunk 9 — Supplier Identification Engine. Data access against the
EXISTING supplier master (sync.Suppliers), not a document-extraction-owned
table — this module has no write path into it (doc_import.matched_supplier_code
is a loose reference, no FK, per sql/0001_document_extraction_tables.sql).

Store-scoped: sync.Suppliers' primary key is (store_id, suppliercode) —
tenant_id isn't even part of the key — so every lookup here is filtered by
both tenant_id and store_id, mirroring modules/procurement/supplier_repository.py.

Known schema gap: sync.Suppliers carries no DL (Drug License) number column
today (only the legacy, unsynced dbo.Suppliers in the OrderNMC reference DB
does). find_by_dl_number() is kept as a real step in the GST->DL->Phone->Name
priority chain for when that gap is closed, but always returns no candidates
until then — see the module docstring in supplier_identification_engine.py.
"""

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts

_SELECT_COLUMNS = """
    CAST(s.suppliercode AS VARCHAR(15))    AS supplier_code,
    CAST(RTRIM(s.suppliername) AS VARCHAR(200)) AS supplier_name,
    s.GSTNumber   AS gst_number,
    s.mobilenumber AS phone
"""


def find_by_gst(tenant_id, store_id, gst_number):
    if not store_id or not gst_number:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM sync.Suppliers s
            WHERE s.tenant_id = ? AND s.store_id = ?
              AND (s.isActive = 1 OR s.isActive IS NULL)
              AND UPPER(RTRIM(s.GSTNumber)) = UPPER(?)
            """,
            (tenant_id, store_id, gst_number.strip()),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def find_by_dl_number(tenant_id, store_id, dl_number):
    """Always [] today — see module docstring: sync.Suppliers has no DL
    number column to match against."""
    return []


def find_by_phone(tenant_id, store_id, phone):
    if not store_id or not phone:
        return []
    digits = "".join(c for c in phone if c.isdigit())[-10:]
    if len(digits) < 10:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {_SELECT_COLUMNS}
            FROM sync.Suppliers s
            WHERE s.tenant_id = ? AND s.store_id = ?
              AND (s.isActive = 1 OR s.isActive IS NULL)
              AND RIGHT(REPLACE(REPLACE(REPLACE(ISNULL(s.mobilenumber, ''), '-', ''), ' ', ''), '+', ''), 10) = ?
            """,
            (tenant_id, store_id, digits),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def search_by_name(tenant_id, store_id, name, limit=10):
    """Cheap LIKE prefilter on the first word of the candidate name; the
    caller (supplier_identification_engine.py) does the real fuzzy ranking
    with rapidfuzz over this shortlist, same division of labour as
    product_mapping/engine_service.py's _refine_with_rapidfuzz."""
    if not store_id or not name:
        return []
    first_word = name.strip().split()[0] if name.strip() else ""
    if len(first_word) < 3:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP ({int(limit)}) {_SELECT_COLUMNS}
            FROM sync.Suppliers s
            WHERE s.tenant_id = ? AND s.store_id = ?
              AND (s.isActive = 1 OR s.isActive IS NULL)
              AND RTRIM(s.suppliername) LIKE '%' + ? + '%'
            """,
            (tenant_id, store_id, first_word),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()
