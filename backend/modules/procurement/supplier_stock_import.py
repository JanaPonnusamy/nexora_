"""Supplier Live Stock — schema provisioning + legacy import.

Creates the backing tables (procurement.supplier_stock, supplier_excel_mapping)
and back-fills them from the legacy OrderNMC database, resolving the legacy
``storename`` (store code) to the platform store_id/tenant_id via dbo.stores.

Phase 2 (Excel upload) reuses ``insert_stock_rows`` and the mapping helpers here.
Run ``python -m modules.procurement.supplier_stock_import`` to (re)provision and
import the legacy data.
"""

import io
import os
import re

from config.database import get_connection, _connection_string

# Canonical mapping target -> supplier_stock column. Mapping.column_name uses the
# canonical key (kept compatible with the legacy SupplierExcelMapping values).
CANONICAL = {
    "supplierproductcode": "supplier_product_code",
    "supplierproductname": "supplier_product_name",
    "stock": "available_stock",
    "ptr": "ptr",
    "mrp": "mrp",
    "discount": "discount",
    "discound": "discount",   # legacy spelling
    "packing": "packing",
    "sch": "scheme",
    "scheme": "scheme",
    "free": "free",
    "minqty": "minimum_qty",
}
# The three matches an upload MUST provide before it can be imported.
MANDATORY = ("supplierproductcode", "supplierproductname", "stock")

# Targets offered in the mapping UI (value, label, mandatory).
CANONICAL_TARGETS = [
    ("supplierproductcode", "Supplier Product Code", True),
    ("supplierproductname", "Supplier Product Name", True),
    ("stock", "Stock / Qty", True),
    ("ptr", "PTR", False),
    ("mrp", "MRP", False),
    ("discount", "Discount", False),
    ("packing", "Packing", False),
    ("sch", "Scheme (buy)", False),
    ("free", "Free Qty", False),
    ("minqty", "Min Qty", False),
]

_HEADER_TOKENS = [
    "product code", "product name", "stock", "qty", "mrp", "ptr",
    "pack", "scheme", "free", "rack", "min", "discount",
]

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")
_DDL_FILE = os.path.join(_SQL_DIR, "0010_supplier_stock_legacy.sql")

# Legacy source lives on the same SQL Server instance, different database.
_LEGACY_DB = os.getenv("LEGACY_DB_DATABASE", "OrderNMC")


def _legacy_connection():
    import pyodbc
    # Reuse the platform connection string but point at the legacy database.
    cs = _connection_string().replace(
        "DATABASE=" + os.getenv("DB_DATABASE", "NEXORA_PLATFORM") + ";",
        "DATABASE=" + _LEGACY_DB + ";",
    )
    return pyodbc.connect(cs)


def apply_ddl():
    """Create the tables if they do not exist (idempotent; splits on GO)."""
    with open(_DDL_FILE, "r", encoding="utf-8") as fh:
        script = fh.read()
    batches = [b.strip() for b in script.split("\nGO") if b.strip()]
    conn = get_connection()
    try:
        cur = conn.cursor()
        for batch in batches:
            cur.execute(batch)
        conn.commit()
    finally:
        conn.close()


def _stores_by_code(conn):
    cur = conn.cursor()
    cur.execute("SELECT store_code, store_id, tenant_id FROM dbo.stores")
    return {r[0]: (str(r[1]), str(r[2])) for r in cur.fetchall()}


_STOCK_COLS = (
    "tenant_id, store_id, supplier_code, supplier_product_code, supplier_product_name, "
    "product_code, available_stock, ptr, mrp, discount, packing, free, minimum_qty, "
    "scheme, transaction_date, source, is_active, imported_by"
)


def resolve_product_codes(conn, tenant_id=None, store_id=None, supplier_code=None):
    """Populate supplier_stock.product_code (store ProductCode) from
    sync.SupplierProductMatch, once, so the live query needs no runtime match
    join. Optionally scoped to a tenant/store/supplier (used by Excel import)."""
    where = ["ss.product_code IS NULL"]
    params = []
    if tenant_id:
        where.append("ss.tenant_id = ?"); params.append(tenant_id)
    if store_id:
        where.append("ss.store_id = ?"); params.append(store_id)
    if supplier_code:
        where.append("ss.supplier_code = ?"); params.append(supplier_code)
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE ss SET ss.product_code = CAST(spm.ProductCode AS VARCHAR(50))
        FROM procurement.supplier_stock ss
        JOIN sync.SupplierProductMatch spm
            ON spm.tenant_id = ss.tenant_id
           AND spm.store_id = ss.store_id
           AND spm.SupplierCode = ss.supplier_code
           AND spm.SupplierProductCode = ss.supplier_product_code
        WHERE {" AND ".join(where)}
        OPTION (HASH JOIN)
        """,
        tuple(params),
    )
    return cur.rowcount


def insert_stock_rows(conn, rows):
    """Bulk-insert prepared supplier_stock tuples (order matches ``_STOCK_COLS``)."""
    if not rows:
        return 0
    cur = conn.cursor()
    cur.fast_executemany = True
    placeholders = ",".join(["?"] * 18)
    cur.executemany(
        f"INSERT INTO procurement.supplier_stock ({_STOCK_COLS}) VALUES ({placeholders})",
        rows,
    )
    return len(rows)


def import_legacy(imported_by="legacy-import"):
    """Copy OrderNMC.SupplierStock + SupplierExcelMapping into the platform."""
    apply_ddl()

    dest = get_connection()
    src = _legacy_connection()
    try:
        stores = _stores_by_code(dest)
        cur = dest.cursor()

        # --- Supplier stock (replace prior legacy load, keep Excel imports) ---
        cur.execute("DELETE FROM procurement.supplier_stock WHERE source = 'legacy'")

        scur = src.cursor()
        scur.execute(
            "SELECT suppliercode, supplierproductcode, supplierproductname, mrp, ptr, "
            "stock, discound, packing, storename, sch, free, transactiondate, minqty "
            "FROM SupplierStock"
        )
        stock_rows, skipped = [], 0
        for r in scur.fetchall():
            store = stores.get((r.storename or "").strip())
            if not store:
                skipped += 1
                continue
            store_id, tenant_id = store
            stock_rows.append((
                tenant_id, store_id, r.suppliercode, r.supplierproductcode,
                r.supplierproductname, None, r.stock, r.mrp, r.ptr, r.discound,
                r.packing, r.free, r.minqty, r.sch, r.transactiondate,
                "legacy", 1, imported_by,
            ))
        inserted = insert_stock_rows(dest, stock_rows)
        dest.commit()

        # Resolve store ProductCode once so the live-stock query stays cheap.
        resolved = resolve_product_codes(dest)
        dest.commit()

        # --- Excel header mapping ---
        cur.execute("DELETE FROM procurement.supplier_excel_mapping")
        scur.execute(
            "SELECT SupplierCode, SupplierColumnName, ColumnName, StoreName "
            "FROM SupplierExcelMapping"
        )
        map_rows, map_skipped = [], 0
        for r in scur.fetchall():
            store = stores.get((r.StoreName or "").strip())
            if not store:
                map_skipped += 1
                continue
            store_id, tenant_id = store
            map_rows.append((tenant_id, store_id, r.SupplierCode,
                             r.SupplierColumnName, r.ColumnName))
        if map_rows:
            mcur = dest.cursor()
            mcur.fast_executemany = True
            mcur.executemany(
                "INSERT INTO procurement.supplier_excel_mapping "
                "(tenant_id, store_id, supplier_code, supplier_column_name, column_name) "
                "VALUES (?,?,?,?,?)",
                map_rows,
            )

        dest.commit()
        return {
            "stock_inserted": inserted, "stock_skipped": skipped,
            "product_codes_resolved": resolved,
            "mappings_inserted": len(map_rows), "mappings_skipped": map_skipped,
        }
    finally:
        src.close()
        dest.close()


# ---------------------------------------------------------------------------
# Excel import (Phase 2) — normalize a supplier's stock file and replace their
# live stock for the store. Normalization mirrors D:\VBDOTNET\Mapping\free.py:
# skip the junk rows above the real header, group duplicates (sum Stock), and
# parse a scheme like "10 F 1" into buy/free.
# ---------------------------------------------------------------------------

def parse_scheme(text):
    """'10 F 1' / '10+1' -> (10, 1); anything else -> (0, 0)."""
    if text is None:
        return 0, 0
    s = str(text).upper().strip()
    m = re.search(r"(\d+)\s*(?:F|\+)\s*(\d+)", s)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _read_matrix(file_bytes, filename):
    """Read an .xls/.xlsx into a list-of-lists (no header assumption)."""
    import pandas as pd
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    engine = "xlrd" if ext == "xls" else "openpyxl"
    raw = pd.read_excel(io.BytesIO(file_bytes), header=None, engine=engine, dtype=object)
    return raw.where(raw.notna(), None).values.tolist()


def _detect_header_row(matrix, known_headers):
    """First row (scan 15) that looks like a header: >=2 cells match a known
    supplier-column name or a common token. Falls back to legacy skiprows=5."""
    tokens = [t.lower() for t in known_headers] + _HEADER_TOKENS
    for i in range(min(15, len(matrix))):
        cells = [str(c).strip().lower() for c in matrix[i] if c is not None and str(c).strip()]
        if len(cells) < 2:
            continue
        if sum(1 for c in cells if any(tok in c for tok in tokens)) >= 2:
            return i
    return 5 if len(matrix) > 5 else 0


def preview_excel(file_bytes, filename, existing_map):
    """Return detected headers, a few sample rows and a suggested mapping.

    existing_map: {supplier_column_name(lower): canonical_column} from the DB.
    Suggestion = saved mapping first, then a fuzzy auto-match for the mandatory
    three so the user usually just confirms.
    """
    matrix = _read_matrix(file_bytes, filename)
    hi = _detect_header_row(matrix, list(existing_map.keys()))
    headers = [("" if c is None else str(c).strip()) for c in matrix[hi]]
    sample = [
        [("" if c is None else str(c)) for c in row]
        for row in matrix[hi + 1: hi + 9]
    ]

    def guess(header):
        h = header.strip().lower()
        if not h:
            return ""
        if h in existing_map:
            return existing_map[h]
        if "product code" in h or h in ("code", "pcode"):
            return "supplierproductcode"
        if "product name" in h or h in ("name", "item", "product"):
            return "supplierproductname"
        if "stock" in h or "qty" in h or "quantity" in h:
            return "stock"
        if h == "ptr" or "rate" in h:
            return "ptr"
        if h == "mrp":
            return "mrp"
        if "pack" in h:
            return "packing"
        if "scheme" in h or h == "sch":
            return "sch"
        if "free" in h:
            return "free"
        if "min" in h:
            return "minqty"
        if "disc" in h:
            return "discount"
        return ""

    suggested = {h: guess(h) for h in headers if h}
    return {
        "headers": [h for h in headers if h],
        "sample": sample,
        "suggested": suggested,
        "targets": [{"value": v, "label": lbl, "mandatory": m} for v, lbl, m in CANONICAL_TARGETS],
    }


def _to_num(v, cast, default=None):
    if v is None or str(v).strip() == "":
        return default
    try:
        return cast(str(v).strip())
    except (ValueError, TypeError):
        return default


def save_mapping(conn, tenant_id, store_id, supplier_code, mapping, created_by=None):
    """Replace the saved header map for a supplier+store with ``mapping``
    ({excel_header: canonical_column}, ignored/empty entries dropped)."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM procurement.supplier_excel_mapping "
        "WHERE tenant_id = ? AND store_id = ? AND supplier_code = ?",
        (tenant_id, store_id, supplier_code),
    )
    rows = [
        (tenant_id, store_id, supplier_code, header, canon, created_by)
        for header, canon in mapping.items()
        if canon and canon in CANONICAL
    ]
    if rows:
        cur.fast_executemany = True
        cur.executemany(
            "INSERT INTO procurement.supplier_excel_mapping "
            "(tenant_id, store_id, supplier_code, supplier_column_name, column_name, created_by) "
            "VALUES (?,?,?,?,?,?)",
            rows,
        )
    return len(rows)


def import_excel(tenant_id, store_id, supplier_code, file_bytes, filename,
                 mapping, imported_by=None):
    """Normalize + REPLACE a supplier's live stock for the store from an upload.

    mapping: {excel_header: canonical_column}. Must cover the mandatory three.
    """
    from fastapi import HTTPException

    inv = {}  # canonical -> excel header
    for header, canon in (mapping or {}).items():
        if canon and canon in CANONICAL:
            inv[canon] = header
    missing = [m for m in MANDATORY if m not in inv]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Map the required columns first: " + ", ".join(missing),
        )

    matrix = _read_matrix(file_bytes, filename)
    hi = _detect_header_row(matrix, [h.lower() for h in mapping.keys()])
    headers = [("" if c is None else str(c).strip()) for c in matrix[hi]]
    idx = {h: i for i, h in enumerate(headers)}

    def col(canon):
        h = inv.get(canon)
        return idx.get(h) if h is not None else None

    ci_code, ci_name, ci_stock = col("supplierproductcode"), col("supplierproductname"), col("stock")
    ci_ptr, ci_mrp = col("ptr"), col("mrp")
    ci_disc, ci_pack = col("discount"), col("packing")
    ci_sch, ci_free, ci_min = col("sch"), col("free"), col("minqty")

    # 1) Build + 2) merge duplicates (sum stock) keyed on product code + name.
    merged = {}
    for row in matrix[hi + 1:]:
        def g(i):
            return row[i] if (i is not None and i < len(row)) else None
        code = g(ci_code)
        name = g(ci_name)
        if (code is None or str(code).strip() == "") and (name is None or str(name).strip() == ""):
            continue
        key = (str(code).strip(), str(name).strip())
        stock = _to_num(g(ci_stock), float, 0.0) or 0.0
        sch, free = 0, 0
        if ci_sch is not None:
            sch, free = parse_scheme(g(ci_sch))
        if ci_free is not None:
            free = _to_num(g(ci_free), int, free) or free
        if key in merged:
            merged[key]["available_stock"] += stock
        else:
            merged[key] = {
                "supplier_product_code": str(code).strip() if code is not None else None,
                "supplier_product_name": str(name).strip() if name is not None else None,
                "available_stock": stock,
                "ptr": _to_num(g(ci_ptr), float),
                "mrp": _to_num(g(ci_mrp), float),
                "discount": (str(g(ci_disc)).strip() if g(ci_disc) is not None else None),
                "packing": (str(g(ci_pack)).strip() if g(ci_pack) is not None else None),
                "scheme": sch or None,
                "free": free or None,
                "minimum_qty": _to_num(g(ci_min), int),
            }

    conn = get_connection()
    try:
        # Persist the mapping so the next upload just confirms.
        save_mapping(conn, tenant_id, store_id, supplier_code, mapping, imported_by)

        # REPLACE this supplier's stock for the store.
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM procurement.supplier_stock "
            "WHERE tenant_id = ? AND store_id = ? AND supplier_code = ?",
            (tenant_id, store_id, supplier_code),
        )

        rows = [(
            tenant_id, store_id, supplier_code, r["supplier_product_code"],
            r["supplier_product_name"], None, r["available_stock"], r["ptr"], r["mrp"],
            r["discount"], r["packing"], r["free"], r["minimum_qty"], r["scheme"],
            None, "excel", 1, imported_by,
        ) for r in merged.values()]
        inserted = insert_stock_rows(conn, rows)
        conn.commit()

        # Resolve store ProductCode for just this supplier (fast, scoped).
        resolved = resolve_product_codes(conn, tenant_id, store_id, supplier_code)
        conn.commit()
        return {"inserted": inserted, "product_codes_resolved": resolved}
    finally:
        conn.close()


if __name__ == "__main__":
    print(import_legacy())
