"""Excel preview/import helpers for procurement.supplier_stock.

This importer is platform-only: it writes to NEXORA_PLATFORM through
config.database and does not read any legacy database.

Normalization mirrors the daily desktop tool ``D:\\VBDOTNET\\Mapping\\free.py``
(and the procurement importer in ``modules.procurement.supplier_stock_import``):

* every supplier ships a differently-shaped file, so the buyer maps each Excel
  column to one of our canonical fields (saved per supplier for next time);
* the real header is auto-detected — supplier exports often carry a title/blank
  band above the column names, so we no longer assume row 1;
* both ``.xlsx`` and legacy ``.xls`` are read (pandas picks the engine from the
  file's own magic bytes, so no filename is required);
* duplicate product rows are merged, **summing** the stock;
* a combined scheme cell like ``"10 F 1"`` is split into buy/free.
"""

from io import BytesIO

import pandas as pd

from modules.supplier_stock_analysis import repository
# Reuse the proven scheme parser + total-row detector so both importers behave
# identically.
from modules.procurement.supplier_stock_import import parse_scheme, looks_total_row

TARGETS = [
    {"value": "supplier_product_code", "label": "Supplier Product Code", "mandatory": True},
    {"value": "supplier_product_name", "label": "Supplier Product Name", "mandatory": True},
    {"value": "available_stock", "label": "Stock / Qty", "mandatory": True},
    {"value": "ptr", "label": "PTR", "mandatory": False},
    {"value": "mrp", "label": "MRP", "mandatory": False},
    {"value": "discount", "label": "Discount", "mandatory": False},
    {"value": "packing", "label": "Packing", "mandatory": False},
    {"value": "scheme", "label": "Scheme (buy)", "mandatory": False},
    {"value": "free", "label": "Free Qty", "mandatory": False},
    {"value": "minimum_qty", "label": "Min Qty", "mandatory": False},
    {"value": "transaction_date", "label": "Transaction Date", "mandatory": False},
]

# Exact normalized-header -> target (fast path for known supplier headers).
_SUGGESTIONS = {
    "code": "supplier_product_code",
    "productcode": "supplier_product_code",
    "itemcode": "supplier_product_code",
    "pcode": "supplier_product_code",
    "name": "supplier_product_name",
    "productname": "supplier_product_name",
    "itemname": "supplier_product_name",
    "product": "supplier_product_name",
    "stock": "available_stock",
    "qty": "available_stock",
    "quantity": "available_stock",
    "ptr": "ptr",
    "rate": "ptr",
    "mrp": "mrp",
    "discount": "discount",
    "disc": "discount",
    "discound": "discount",   # legacy spelling
    "packing": "packing",
    "pack": "packing",
    "scheme": "scheme",
    "sch": "scheme",
    "free": "free",
    "minqty": "minimum_qty",
    "minimumqty": "minimum_qty",
}

# Cells that make a row "look like" a header (used to find the real header row).
_HEADER_TOKENS = [
    "product code", "product name", "stock", "qty", "quantity", "mrp", "ptr",
    "pack", "scheme", "free", "rack", "min", "discount", "rate", "code", "name",
]


def _norm(value):
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _guess(header):
    """Best canonical target for a header: exact normalized hit, then phrase match."""
    h = str(header or "").strip().lower()
    if not h:
        return ""
    exact = _SUGGESTIONS.get(_norm(h))
    if exact:
        return exact
    if "product code" in h or "item code" in h:
        return "supplier_product_code"
    if "product name" in h or "item name" in h or h in ("item", "description"):
        return "supplier_product_name"
    if "stock" in h or "qty" in h or "quantity" in h:
        return "available_stock"
    if "scheme" in h:
        return "scheme"
    if "free" in h:
        return "free"
    if "pack" in h:
        return "packing"
    if "disc" in h:
        return "discount"
    if h == "mrp":
        return "mrp"
    if h == "ptr" or "rate" in h:
        return "ptr"
    if "min" in h:
        return "minimum_qty"
    return ""


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value, default=None):
    if value in (None, ""):
        return default
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _read_matrix(file_bytes):
    """Read an .xls/.xlsx upload into (sheet_name, list-of-lists) with no header
    assumption. pandas selects xlrd/openpyxl from the file's own magic bytes, so
    both formats work without a filename."""
    xls = pd.ExcelFile(BytesIO(file_bytes))
    sheet_name = xls.sheet_names[0] if xls.sheet_names else ""
    raw = xls.parse(0, header=None, dtype=object)
    matrix = raw.where(raw.notna(), None).values.tolist()
    return sheet_name, matrix


def _detect_header_row(matrix, known_headers):
    """First row (scan up to 15) that looks like a header: >=2 cells match a
    saved supplier-column name or a common token. Falls back to the first row."""
    tokens = [t.lower() for t in known_headers] + _HEADER_TOKENS
    for i in range(min(15, len(matrix))):
        cells = [str(c).strip().lower() for c in matrix[i] if c is not None and str(c).strip()]
        if len(cells) < 2:
            continue
        if sum(1 for c in cells if any(tok in c for tok in tokens)) >= 2:
            return i
    return 0


def preview(file_bytes):
    sheet_name, matrix = _read_matrix(file_bytes)
    if not matrix:
        return {
            "sheet_name": sheet_name, "row_count": 0, "headers": [],
            "suggested_mapping": {}, "targets": TARGETS, "sample_rows": [],
        }
    hi = _detect_header_row(matrix, [])
    headers = [("" if c is None else str(c).strip()) for c in matrix[hi]]
    headers = [h for h in headers if h]
    suggested = {h: _guess(h) for h in headers}
    sample = []
    for row in matrix[hi + 1: hi + 11]:
        sample.append({headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))})
    return {
        "sheet_name": sheet_name,
        "row_count": max(len(matrix) - hi - 1, 0),
        "headers": headers,
        "suggested_mapping": suggested,
        "targets": TARGETS,
        "sample_rows": sample,
    }


def import_file(tenant_id, store_id, supplier_code, file_bytes, mapping, imported_by=None):
    # mapping: {excel_header: target}. Invert to {target: excel_header}.
    reverse = {target: source for source, target in (mapping or {}).items() if target}
    missing = [t["value"] for t in TARGETS if t["mandatory"] and t["value"] not in reverse]
    if missing:
        return {"success": False, "error": "Missing required mapping", "missing": missing}

    sheet_name, matrix = _read_matrix(file_bytes)
    hi = _detect_header_row(matrix, [h.lower() for h in (mapping or {}).keys()])
    headers = [("" if c is None else str(c).strip()) for c in matrix[hi]]
    idx = {h: i for i, h in enumerate(headers)}

    def col(target):
        h = reverse.get(target)
        return idx.get(h) if h is not None else None

    ci_code, ci_name, ci_stock = col("supplier_product_code"), col("supplier_product_name"), col("available_stock")
    ci_ptr, ci_mrp = col("ptr"), col("mrp")
    ci_disc, ci_pack = col("discount"), col("packing")
    ci_sch, ci_free, ci_min = col("scheme"), col("free"), col("minimum_qty")
    ci_txn = col("transaction_date")

    # Build + merge duplicates (sum stock) keyed on product code + name.
    merged = {}
    for row in matrix[hi + 1:]:
        def g(i):
            return row[i] if (i is not None and i < len(row)) else None
        code = g(ci_code)
        code_str = "" if code is None else str(code).strip()
        # Drop rows with an empty product code (division section headers, blank
        # spacers) and division/sub/grand-total lines.
        if code_str == "" or looks_total_row(code_str):
            continue
        name = g(ci_name)
        name_str = "" if name is None else str(name).strip()
        key = (code_str, name_str)
        stock = _number(g(ci_stock)) or 0.0
        # Split a combined "10 F 1" scheme; a dedicated Free column wins if mapped.
        sch, free = (parse_scheme(g(ci_sch)) if ci_sch is not None else (0, 0))
        if ci_free is not None:
            free = _int(g(ci_free), free) or free
        if key in merged:
            merged[key]["available_stock"] = (merged[key]["available_stock"] or 0.0) + stock
            continue
        merged[key] = {
            "supplier_product_code": code_str,
            "supplier_product_name": name_str,
            "available_stock": stock,
            "ptr": _number(g(ci_ptr)),
            "mrp": _number(g(ci_mrp)),
            "discount": (str(g(ci_disc)).strip() if g(ci_disc) is not None else None),
            "packing": (str(g(ci_pack)).strip() if g(ci_pack) is not None else None),
            "free": free or None,
            "minimum_qty": _int(g(ci_min)),
            "scheme": sch or None,
            "transaction_date": g(ci_txn),
        }

    result = repository.replace_supplier_stock(
        tenant_id, store_id, supplier_code, list(merged.values()), imported_by or "desktop-import"
    )
    return {"success": True, **result}
