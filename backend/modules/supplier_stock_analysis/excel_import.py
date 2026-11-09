"""Excel preview/import helpers for the central OrderNMC.SupplierStock table.

Imports REPLACE the supplier's rows for the selected store (storename = store
code) in OrderNMC.SupplierStock, and the column mapping is saved per supplier
in OrderNMC.SupplierExcelMapping -- the same tables the legacy VB import used.

Normalization mirrors the daily desktop tool ``D:\\VBDOTNET\\Mapping\\free.py``
(and the procurement importer in ``modules.procurement.supplier_stock_import``):

* every supplier ships a differently-shaped file, so the buyer maps each Excel
  column to one of our canonical fields (saved per supplier for next time);
* the real header is auto-detected — supplier exports often carry a title/blank
  band above the column names, so we no longer assume row 1;
* both ``.xlsx`` and legacy ``.xls`` are read (pandas picks the engine from the
  file's own magic bytes, so no filename is required);
* duplicate product rows are merged, **summing** the stock (keyed on the
  product code -- OrderNMC.SupplierStock's PK is supplier+product+store);
* a combined scheme cell like ``"10 F 1"`` (e.g. "Batch Free Scheme") is
  split into sch/free; a plain number is taken as sch.
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
    {"value": "rack", "label": "Rack", "mandatory": False},
]

# Target <-> legacy OrderNMC column name (what SupplierExcelMapping.ColumnName
# stores, so mappings saved by the old VB import keep working).
_LEGACY_COLUMN = {
    "supplier_product_code": "supplierproductcode",
    "supplier_product_name": "supplierproductname",
    "available_stock": "stock",
    "ptr": "ptr",
    "mrp": "mrp",
    "discount": "discound",
    "packing": "packing",
    "scheme": "sch",
    "free": "free",
    "minimum_qty": "minqty",
    "rack": "rack",
}
_TARGET_BY_LEGACY = {v: k for k, v in _LEGACY_COLUMN.items()}

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
    "batchfreescheme": "scheme",
    "rack": "rack",
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
    if "rack" in h:
        return "rack"
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


# Fixed-width PRODUCT.TXT layout used by the legacy VB6 stock loader
# (Command3_Click): Mid$(ln, start, len), 1-based, converted to 0-based slices.
_TXT_FIELD_SLICES = [
    (0, 6),     # supplier product code
    (7, 32),    # product name
    (33, 40),   # pack
    (41, 66),   # manufacturer
    (67, 77),   # MRP
    (78, 87),   # qty
    (88, 97),   # free
    (98, 107),  # stock
]
_TXT_HEADERS = [
    "Supplier Product Code", "Supplier Product Name", "Packing", "Manufacturer",
    "MRP", "Scheme", "Free", "Stock",
]


def _is_fixed_width_txt(file_bytes):
    """PRODUCT.TXT isn't an Excel file -- xlrd/openpyxl magic bytes won't match
    (PK.. for xlsx, 0xD0CF11E0 for xls); everything else is treated as the
    legacy semicolon-delimited fixed-width export."""
    head = file_bytes[:8]
    return not (head.startswith(b"PK") or head.startswith(b"\xd0\xcf\x11\xe0"))


def _read_txt_matrix(file_bytes):
    text = file_bytes.decode("utf-8", errors="replace")
    matrix = [_TXT_HEADERS]
    for line in text.splitlines():
        if not line.strip():
            continue
        row = [line[a:b].strip() or None for a, b in _TXT_FIELD_SLICES]
        matrix.append(row)
    return "PRODUCT.TXT", matrix


def _read_matrix(file_bytes):
    """Read an .xls/.xlsx/.txt upload into (sheet_name, list-of-lists) with no
    header assumption. pandas selects xlrd/openpyxl from the file's own magic
    bytes for Excel; a fixed-width PRODUCT.TXT export is parsed by column
    position (see _TXT_FIELD_SLICES) and given a synthetic header row so it
    flows through the same preview/mapping/import path as Excel uploads."""
    if _is_fixed_width_txt(file_bytes):
        return _read_txt_matrix(file_bytes)
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


def _saved_mapping(tenant_id, store_id, supplier_code):
    """{excel header (lower): target} from the supplier's saved mapping."""
    if not (tenant_id and store_id and supplier_code):
        return {}
    saved = repository.saved_excel_mapping(tenant_id, store_id, supplier_code)
    return {
        header.lower(): _TARGET_BY_LEGACY[column.lower()]
        for header, column in saved.items()
        if column.lower() in _TARGET_BY_LEGACY
    }


def preview(file_bytes, tenant_id=None, store_id=None, supplier_code=None):
    saved = _saved_mapping(tenant_id, store_id, supplier_code)
    sheet_name, matrix = _read_matrix(file_bytes)
    if not matrix:
        return {
            "sheet_name": sheet_name, "row_count": 0, "headers": [],
            "suggested_mapping": {}, "targets": TARGETS, "sample_rows": [],
        }
    hi = _detect_header_row(matrix, list(saved))
    headers = [("" if c is None else str(c).strip()) for c in matrix[hi]]
    headers = [h for h in headers if h]
    suggested = {h: saved.get(h.lower()) or _guess(h) for h in headers}
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
        "saved_mapping": bool(saved),
    }


def _parse_rows(file_bytes, mapping):
    """Shared by import_file / import_file_bulk: mapping {excel_header: target}
    -> deduped, normalized rows ready for repository.replace_supplier_stock*.
    Returns (rows, missing_targets); rows is [] when missing_targets is non-empty."""
    reverse = {target: source for source, target in (mapping or {}).items() if target}
    missing = [t["value"] for t in TARGETS if t["mandatory"] and t["value"] not in reverse]
    if missing:
        return [], missing

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
    ci_txn, ci_rack = col("transaction_date"), col("rack")

    # Build + merge duplicates (sum stock) keyed on the product code -- the
    # OrderNMC.SupplierStock PK is (supplier, product code, store).
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
        key = code_str
        stock = _number(g(ci_stock)) or 0.0
        # Split a combined "10 F 1" scheme; a dedicated Free column wins if mapped.
        sch, free = (parse_scheme(g(ci_sch)) if ci_sch is not None else (0, 0))
        if not sch and ci_sch is not None:
            sch = _int(g(ci_sch), 0)  # a plain "sch" column (already split)
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
            "rack": (str(g(ci_rack)).strip() if g(ci_rack) is not None else None),
        }
    return list(merged.values()), []


def import_file(tenant_id, store_id, supplier_code, file_bytes, mapping, imported_by=None):
    rows, missing = _parse_rows(file_bytes, mapping)
    if missing:
        return {"success": False, "error": "Missing required mapping", "missing": missing}

    result = repository.replace_supplier_stock(
        tenant_id, store_id, supplier_code, rows, imported_by or "desktop-import"
    )
    repository.save_excel_mapping(
        tenant_id, store_id, supplier_code,
        {source: _LEGACY_COLUMN[target] for source, target in (mapping or {}).items()
         if target in _LEGACY_COLUMN},
    )
    return {"success": True, **result}


def bulk_import_stores(tenant_id, supplier_code):
    """Every active store in tenant_id whose OrderSuppliers carries this exact
    supplier code -- the confirm list shown before a bulk import commits."""
    return repository.list_stores_with_supplier_code(tenant_id, supplier_code)


def import_file_bulk(tenant_id, supplier_code, file_bytes, mapping, store_ids=None, imported_by=None):
    """Same REPLACE as import_file, written to every active store in
    tenant_id that has this exact supplier code (or just store_ids, when the
    operator deselected some from the confirm list) -- one parse, one
    mapping save (keyed by supplier_code, not per-store), many stores."""
    rows, missing = _parse_rows(file_bytes, mapping)
    if missing:
        return {"success": False, "error": "Missing required mapping", "missing": missing}

    stores = repository.list_stores_with_supplier_code(tenant_id, supplier_code)
    if store_ids is not None:
        wanted = {str(s) for s in store_ids}
        stores = [s for s in stores if s["store_id"] in wanted]
    if not stores:
        return {"success": False, "error": "No matching store found for this supplier code."}

    store_codes = [s["store_code"] for s in stores]
    results = repository.replace_supplier_stock_bulk(
        tenant_id, supplier_code, rows, store_codes, imported_by or "desktop-import"
    )
    # Saved mapping is keyed by (tenant, store, supplier) -- persist it once per
    # store so each store's next single-store import still prefills correctly.
    legacy_columns = {
        source: _LEGACY_COLUMN[target] for source, target in (mapping or {}).items()
        if target in _LEGACY_COLUMN
    }
    for store in stores:
        repository.save_excel_mapping(tenant_id, store["store_id"], supplier_code, legacy_columns)

    return {
        "success": True,
        "stores": [
            {
                "store_id": store["store_id"],
                "store_code": store["store_code"],
                "store_name": store.get("store_name"),
                **results.get(store["store_code"], {"imported": 0, "product_codes_resolved": 0}),
            }
            for store in stores
        ],
    }
