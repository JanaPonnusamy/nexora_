"""Bulk-assign + Excel export for the Order Workspace "By Supplier" screen.

Ports the tail of the legacy WinForms Form1.btnExport_Click sequence:
UpdateDatabase() (bulk assign every grid row to the current supplier) then
ExportSelectedColumnsFromGrid() (the Excel build) -- Form1.vb, OrderManagement
WinForms project, ~lines 4441-4713.

Deliberately NOT ported: UpdateSupplierStockAfterExport(), which decremented
SupplierStock.stock by OrderQty*Pack after every export. Nexora already has an
independent, sync-driven supplier_stock pipeline (see the Supplier Live Stock
module); reproducing the legacy manual decrement here risks double-counting
against that sync, so this module intentionally stops once the Excel file is
built. This is an explicit product decision, not an oversight.
"""
import datetime
import io
import logging
import zipfile

from modules.legacy_order import repository

logger = logging.getLogger(__name__)

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS_MEDIA_TYPE = "application/vnd.ms-excel"
ZIP_MEDIA_TYPE = "application/zip"


class NoExportableRows(Exception):
    """No OrderQty>0 rows for this store/supplier -- nothing to assign or export."""


class ExportGenerationFailed(Exception):
    """Bulk assignment already committed; only the Excel build failed."""


class ExportResult:
    def __init__(self, content, filename, media_type, count, supplier_name):
        self.content = content
        self.filename = filename
        self.media_type = media_type
        self.count = count
        self.supplier_name = supplier_name


# --------------------------------------------------------------------------
# Category prediction -- port of Form1.PredictExportCategory /
# NormalizeExportCategory (Form1.vb ~lines 4407-4435).
# --------------------------------------------------------------------------

def _normalize_category(raw):
    if not raw or not raw.strip():
        return ""
    t = raw.strip().upper()
    for needle, tag in (
        ("TAB", "TAB"), ("SYP", "SYP"), ("SYRUP", "SYP"), ("PASTE", "PASTE"),
        ("VET", "VET"), ("INH", "INH"), ("RC", "RC"), ("RESP", "RESP"),
    ):
        if needle in t:
            return tag
    return ""


def _predict_category(sub_location, product_name, unit_description):
    from_sub = _normalize_category(sub_location)
    if from_sub:
        return from_sub
    text = f"{product_name or ''} {unit_description or ''}".upper()
    if "ROTACAP" in text:
        return "RC"
    if "INHALER" in text or "INHALLER" in text or " INH" in text:
        return "INH"
    if "RESPULE" in text or "RESP " in text or text.endswith("RESP"):
        return "RESP"
    if "PASTE" in text:
        return "PASTE"
    if "SUSPENSION" in text or "SYRUP" in text or " SYP" in text or text.endswith("SYP"):
        return "SYP"
    if "VET" in text:
        return "VET"
    if "TABLET" in text or " TAB" in text or text.endswith("TAB"):
        return "TAB"
    return "OTHER"


# --------------------------------------------------------------------------
# Filename -- port of Form1.SafeFileName (Form1.vb ~lines 4656-4665).
# --------------------------------------------------------------------------

_INVALID_FILENAME_CHARS = set('<>:"/\\|?*') | {chr(c) for c in range(32)}


def _safe_file_name(name):
    cleaned = "".join("_" if ch in _INVALID_FILENAME_CHARS else ch for ch in name)
    cleaned = cleaned.replace("[", "(").replace("]", ")")
    return cleaned.strip()


# --------------------------------------------------------------------------
# Workbook -- port of Form1.ExportSelectedColumnsFromGrid's column layout,
# header styling and S.No./OrderQty cell fills (Form1.vb ~lines 4441-4634).
# ProductCode is additionally forced to a TEXT cell (NumberFormat "@") --
# the legacy routine never did this (ProductCode is a plain int column in
# this schema), kept here only as a cheap safety margin.
# --------------------------------------------------------------------------

def _format_product_code(value):
    """ordermanagement.productcode round-trips through pyodbc as a Python
    float (e.g. 9810.0), not an int, even though it's always a whole number.
    str(9810.0) == "9810.0" -- writing that straight into the text cell would
    silently corrupt every exported ProductCode with a bogus ".0" suffix.
    Only numeric types get this treatment -- a string value is left exactly
    as-is (never round-tripped through float()), so a genuine text code with
    leading zeros is never touched."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) == int(value):
            return str(int(value))
    return str(value)


def _build_workbook(rows, has_rack):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    headers = ["S.No.", "ProductName", "OrderQty", "SaleUnit", "MRP", "ProductCode", "Discount", "Category", "SubLocation"]
    if has_rack:
        headers.append("Rack")

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)

    # Owner request (2026-10-22): the exported sheet rendered with NO cell
    # borders at all and no header background -- only the Order Qty fill --
    # which read as unfinished next to the legacy VB.NET app's output. Same
    # border/header-fill treatment _build_workbook_custom already had
    # (thin interior, thick outer edge + header row), applied here too so
    # BOTH export paths (fixed legacy layout vs. operator-picked columns)
    # look identical, not just the custom one.
    header_fill = PatternFill("solid", fgColor="D9E6F2")
    sno_fill = PatternFill("solid", fgColor="FFFFE0")
    qty_fill = PatternFill("solid", fgColor="90EE90")
    thin = Side(style="thin", color="B7B7B7")
    thick = Side(style="medium", color="404040")
    n_cols = len(headers)
    n_rows = len(rows) + 1

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.fill = header_fill
        cell.border = Border(top=thick, bottom=thick,
                              left=thick if cell.column == 1 else thin,
                              right=thick if cell.column == n_cols else thin)

    for i, row in enumerate(rows, start=1):
        values = [
            i,
            row.get("ProductName") or "",
            row.get("OrderQty") or 0,
            row.get("SaleUnit") or "",
            row.get("MRP") or 0,
            _format_product_code(row.get("ProductCode")),
            row.get("Discount") if has_rack else "",
            row.get("Category") or "",
            row.get("SubLocation") or "",
        ]
        if has_rack:
            values.append(row.get("Rack") or "")
        ws.append(values)

        excel_row = ws[i + 1]
        excel_row[0].fill = sno_fill
        excel_row[0].font = Font(bold=True)
        excel_row[0].alignment = Alignment(horizontal="center")
        excel_row[2].fill = qty_fill
        excel_row[2].font = Font(bold=True)
        excel_row[2].alignment = Alignment(horizontal="center")
        code_cell = excel_row[5]
        code_cell.number_format = "@"
        code_cell.value = _format_product_code(row.get("ProductCode"))

        is_last_row = (i + 1) == n_rows
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=i + 1, column=c)
            cell.border = Border(
                top=thin, bottom=thick if is_last_row else thin,
                left=thick if c == 1 else thin, right=thick if c == n_cols else thin,
            )

    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 40)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------
# Configurable export — operator-chosen column subset + xlsx/csv, used when
# the request supplies `columns`/`file_format`. ProductCode/ProductName/
# OrderQty are always included regardless of selection (enforced here, not
# just client-side, since this is a public API contract). Keeps the legacy
# _build_workbook() path above completely untouched for existing callers
# that omit `columns` — this is strictly additive.
# --------------------------------------------------------------------------

_EXPORT_COLUMN_MAP = {
    "product_code": ("ProductCode", lambda r: _format_product_code(r.get("ProductCode"))),
    "product_name": ("ProductName", lambda r: r.get("ProductName") or ""),
    "order_qty": ("OrderQty", lambda r: r.get("OrderQty") or 0),
    "sale_unit": ("SaleUnit", lambda r: r.get("SaleUnit") or ""),
    "mrp": ("MRP", lambda r: r.get("MRP") or 0),
    "discount": ("Discount", lambda r: r.get("Discount") or ""),
    "category": ("Category", lambda r: r.get("Category") or ""),
    "sub_location": ("SubLocation", lambda r: r.get("SubLocation") or ""),
    "rack": ("Rack", lambda r: r.get("Rack") or ""),
}
_EXPORT_REQUIRED_COLUMNS = ("product_code", "product_name", "order_qty")


def _resolve_columns(columns):
    ordered = list(_EXPORT_REQUIRED_COLUMNS)
    for key in columns or []:
        if key in _EXPORT_COLUMN_MAP and key not in ordered:
            ordered.append(key)
    return ordered


def _build_workbook_custom(rows, columns):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    keys = _resolve_columns(columns)
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([_EXPORT_COLUMN_MAP[k][0] for k in keys])

    # Same green the legacy VB.NET export used for Order Qty (90EE90, see
    # _build_workbook's qty_fill) -- operators expect that column to stand out
    # the same way it always has. Thin border on every used cell, thick on the
    # header row and the whole table's outer edge -- a plain borderless sheet
    # read as unfinished/placeholder next to the legacy app's output.
    qty_fill = PatternFill("solid", fgColor="90EE90")
    thin = Side(style="thin", color="B7B7B7")
    thick = Side(style="medium", color="404040")
    qty_col = keys.index("order_qty") + 1 if "order_qty" in keys else None

    n_rows = len(rows) + 1  # +1 for header
    n_cols = len(keys)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.border = Border(top=thick, bottom=thick,
                              left=thick if cell.column == 1 else thin,
                              right=thick if cell.column == n_cols else thin)

    for row in rows:
        ws.append([_EXPORT_COLUMN_MAP[k][1](row) for k in keys])
        r = ws.max_row
        if "product_code" in keys:
            code_cell = ws.cell(row=r, column=keys.index("product_code") + 1)
            code_cell.number_format = "@"
            code_cell.value = _format_product_code(row.get("ProductCode"))
        is_last_row = r == n_rows
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = Border(
                top=thin, bottom=thick if is_last_row else thin,
                left=thick if c == 1 else thin, right=thick if c == n_cols else thin,
            )
            if c == qty_col:
                cell.fill = qty_fill
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")

    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 40)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_csv_custom(rows, columns):
    import csv

    keys = _resolve_columns(columns)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([_EXPORT_COLUMN_MAP[k][0] for k in keys])
    for row in rows:
        writer.writerow([_EXPORT_COLUMN_MAP[k][1](row) for k in keys])
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens non-ASCII cleanly


# --------------------------------------------------------------------------
# Pending Order export -- there is no legacy VB.NET method for this (the
# only export the WinForms app ever had, ExportSelectedColumnsFromGrid, was
# wired exclusively to the By Supplier screen's btnExport_Click and always
# assigned status 0->1 first). Reusing that SAME workbook format/style here
# (owner request: Pending export should look like the existing export, not
# a new design) while deliberately dropping the assignment step entirely --
# Pending rows (qtycheck=1, status=0, no supplier yet) must stay status=0;
# this is read-only, same as the Assigned-view export path with no
# product_codes.
# --------------------------------------------------------------------------

_PENDING_COLUMN_MAP = {
    "product_code": ("ProductCode", lambda r: _format_product_code(r.get("ProductCode"))),
    "product_name": ("ProductName", lambda r: r.get("ProductName") or ""),
    "order_qty": ("OrderQty", lambda r: r.get("OrderQty") or 0),
    "sale_unit": ("SaleUnit", lambda r: r.get("SaleUnit") or ""),
    "mrp": ("MRP", lambda r: r.get("MRP") or 0),
    "stock": ("Stock", lambda r: r.get("TotalStock") or 0),
    "sls_qty": ("SlsQty", lambda r: r.get("SLSQty") or 0),
    "max_qty": ("MaxQty", lambda r: r.get("MaxSaleQty") or 0),
    "wanted": ("Wanted", lambda r: r.get("WantedType") or ""),
}
_PENDING_REQUIRED_COLUMNS = ("product_code", "product_name", "order_qty")


def _resolve_pending_columns(columns):
    ordered = list(_PENDING_REQUIRED_COLUMNS)
    for key in columns or []:
        if key in _PENDING_COLUMN_MAP and key not in ordered:
            ordered.append(key)
    if len(ordered) == len(_PENDING_REQUIRED_COLUMNS):
        # No selection supplied -- default to the grid's own full column set
        # instead of just the three required ones.
        ordered = ["product_code", "product_name", "order_qty", "stock", "sale_unit", "sls_qty", "mrp", "max_qty", "wanted"]
    return ordered


def _normalize_pending_row(row):
    """pending_order_rows() returns the lowercase column names from its own
    SQL projection (see repository.pending_order_rows) -- reshape to the
    same PascalCase keys _build_workbook_custom/_build_csv_custom already
    expect, so this reuses those builders unchanged instead of forking a
    parallel Pending-only workbook function."""
    return {
        "ProductCode": row.get("productcode"),
        "ProductName": row.get("productname"),
        "OrderQty": row.get("orderqty"),
        "SaleUnit": row.get("saleunit"),
        "MRP": row.get("mrp"),
        "TotalStock": row.get("totalstock"),
        "SLSQty": row.get("slsqty"),
        "MaxSaleQty": row.get("maxsaleqty"),
        "WantedType": row.get("wantedtype"),
    }


def export_pending_order(store_name, split_size, columns=None, file_format="xlsx", order_no=None):
    rows = [_normalize_pending_row(r) for r in repository.pending_order_rows(store_name)]
    rows = [r for r in rows if (r.get("OrderQty") or 0) > 0]
    if not rows:
        raise NoExportableRows("No pending products with a positive order quantity to export.")

    rows.sort(key=lambda r: r.get("ProductName") or "")
    pending_count = len(rows)

    date_part = datetime.date.today().strftime("%d%m%Y")  # ddmmyyyy -- see export_order
    order_part = order_no if order_no else date_part
    base_name = _safe_file_name(f"Pending {date_part} {order_part}")

    try:
        split_size = int(split_size or 0)
    except (TypeError, ValueError):
        split_size = 0

    if 0 < split_size < len(rows):
        chunks = [rows[i:i + split_size] for i in range(0, len(rows), split_size)]
    else:
        chunks = [rows]

    keys = _resolve_pending_columns(columns)
    file_format = file_format if file_format in ("xlsx", "xls", "csv") else "xls"
    ext = "csv" if file_format == "csv" else file_format

    def build_one(chunk):
        if file_format == "csv":
            import csv
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([_PENDING_COLUMN_MAP[k][0] for k in keys])
            for row in chunk:
                writer.writerow([_PENDING_COLUMN_MAP[k][1](row) for k in keys])
            return buf.getvalue().encode("utf-8-sig")
        if file_format == "xls":
            return _build_workbook_custom_generic_xls(chunk, keys, _PENDING_COLUMN_MAP)
        return _build_workbook_custom_generic(chunk, keys, _PENDING_COLUMN_MAP)

    try:
        if len(chunks) == 1:
            content = build_one(chunks[0])
            filename = f"{base_name}.{ext}"
            media_type = "text/csv" if ext == "csv" else (XLS_MEDIA_TYPE if ext == "xls" else XLSX_MEDIA_TYPE)
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, chunk in enumerate(chunks, start=1):
                    part_name = f"{base_name} Part {idx} of {len(chunks)}.{ext}"
                    zf.writestr(part_name, build_one(chunk))
            content = buf.getvalue()
            filename = f"{base_name}.zip"
            media_type = ZIP_MEDIA_TYPE
    except Exception as exc:
        logger.exception(
            "Pending order export: workbook build failed for store=%s (%s rows)",
            store_name, pending_count,
        )
        raise ExportGenerationFailed("Excel generation failed. No data was changed -- retry the export.") from exc

    return ExportResult(content, filename, media_type, pending_count, "Pending")


def _build_workbook_custom_generic(rows, keys, column_map):
    """Same layout/styling as _build_workbook_custom (green Order Qty column,
    borders, product-code-as-text), generalized to take its own column map
    instead of the By-Supplier-specific _EXPORT_COLUMN_MAP -- so Pending's
    different field set (Stock/Max Qty/Wanted instead of Discount/Category/
    SubLocation/Rack) still gets the identical visual treatment."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append([column_map[k][0] for k in keys])

    qty_fill = PatternFill("solid", fgColor="90EE90")
    thin = Side(style="thin", color="B7B7B7")
    thick = Side(style="medium", color="404040")
    qty_col = keys.index("order_qty") + 1 if "order_qty" in keys else None

    n_cols = len(keys)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        cell.border = Border(top=thick, bottom=thick,
                              left=thick if cell.column == 1 else thin,
                              right=thick if cell.column == n_cols else thin)

    n_rows = len(rows) + 1
    for row in rows:
        ws.append([column_map[k][1](row) for k in keys])
        r = ws.max_row
        if "product_code" in keys:
            code_cell = ws.cell(row=r, column=keys.index("product_code") + 1)
            code_cell.number_format = "@"
            code_cell.value = _format_product_code(row.get("ProductCode"))
        is_last_row = r == n_rows
        for c in range(1, n_cols + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = Border(
                top=thin, bottom=thick if is_last_row else thin,
                left=thick if c == 1 else thin, right=thick if c == n_cols else thin,
            )
            if c == qty_col:
                cell.fill = qty_fill
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center")

    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(width + 2, 40)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------
# .xls (legacy BIFF binary format, Excel 97-2003) -- owner request
# (2026-10-22): some downstream consumer needs the real old binary format,
# not just an .xlsx renamed to .xls. openpyxl cannot write this format at
# all (it is xlsx-only); xlwt is the only maintained-enough library in this
# dependency set that can (already a tracked dependency -- requirements.txt
# -- version 1.3.0, last released ~2015 but functionally complete for this
# use case). xlwt's styling model is a much older, flatter API (easyxf
# strings, not openpyxl's Font/Border/PatternFill objects) and BIFF itself
# caps out at 65,536 rows / 256 columns per sheet -- both completely fine
# for this export's realistic row counts, so no fallback/warning is needed
# for that limit in practice.
# --------------------------------------------------------------------------

def _build_workbook_custom_generic_xls(rows, keys, column_map):
    """xls counterpart of _build_workbook_custom_generic -- same column_map
    pattern (used by export_pending_order), xlwt styling instead of
    openpyxl."""
    import xlwt
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    header_style = _xls_style(bold=True, fill_rgb="pale_blue", border=True, align_center=True, border_thick="medium")
    qty_style = _xls_style(bold=True, fill_rgb="light_green", border=True, align_center=True)
    plain_style = _xls_style(border=True)
    code_style = _xls_style(border=True, num_format="@")
    qty_col_idx = keys.index("order_qty") if "order_qty" in keys else None
    code_col_idx = keys.index("product_code") if "product_code" in keys else None

    for c, key in enumerate(keys):
        ws.write(0, c, column_map[key][0], header_style)

    for r, row in enumerate(rows, start=1):
        for c, key in enumerate(keys):
            value = column_map[key][1](row)
            if c == qty_col_idx:
                ws.write(r, c, value, qty_style)
            elif c == code_col_idx:
                ws.write(r, c, value, code_style)
            else:
                ws.write(r, c, value, plain_style)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _xls_style(bold=False, fill_rgb=None, border=False, align_center=False, border_thick=None, num_format=None):
    """Builds an xlwt easyxf style string. fill_rgb picks the nearest of
    xlwt's fixed 56-color BIFF palette (xlwt has no arbitrary RGB fill --
    only named palette entries), chosen to match this file's existing
    openpyxl colors as closely as that palette allows."""
    import xlwt
    parts = []
    font = "font:"
    if bold:
        font += " bold on,"
    font = font.rstrip(",")
    if font != "font:":
        parts.append(font)
    if align_center:
        parts.append("align: horiz center")
    if fill_rgb:
        parts.append(f"pattern: pattern solid, fore_colour {fill_rgb}")
    if border:
        weight = border_thick or "thin"
        parts.append(f"borders: left {weight}, right {weight}, top {weight}, bottom {weight}")
    xf = xlwt.easyxf("; ".join(parts)) if parts else xlwt.easyxf("")
    if num_format:
        xf.num_format_str = num_format
    return xf


def _build_workbook_xls(rows, has_rack):
    import xlwt
    headers = ["S.No.", "ProductName", "OrderQty", "SaleUnit", "MRP", "ProductCode", "Discount", "Category", "SubLocation"]
    if has_rack:
        headers.append("Rack")

    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    header_style = _xls_style(bold=True, fill_rgb="pale_blue", border=True, align_center=True, border_thick="medium")
    sno_style = _xls_style(bold=True, fill_rgb="light_yellow", border=True, align_center=True)
    qty_style = _xls_style(bold=True, fill_rgb="light_green", border=True, align_center=True)
    plain_style = _xls_style(border=True)
    code_style = _xls_style(border=True, num_format="@")

    for c, label in enumerate(headers):
        ws.write(0, c, label, header_style)

    for i, row in enumerate(rows, start=1):
        values = [
            i, row.get("ProductName") or "", row.get("OrderQty") or 0, row.get("SaleUnit") or "",
            row.get("MRP") or 0, _format_product_code(row.get("ProductCode")),
            row.get("Discount") if has_rack else "", row.get("Category") or "", row.get("SubLocation") or "",
        ]
        if has_rack:
            values.append(row.get("Rack") or "")
        for c, value in enumerate(values):
            if c == 0:
                ws.write(i, c, value, sno_style)
            elif c == 2:
                ws.write(i, c, value, qty_style)
            elif c == 5:
                ws.write(i, c, value, code_style)
            else:
                ws.write(i, c, value, plain_style)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_workbook_custom_xls(rows, columns):
    import xlwt
    keys = _resolve_columns(columns)
    wb = xlwt.Workbook()
    ws = wb.add_sheet("Sheet1")
    header_style = _xls_style(bold=True, fill_rgb="pale_blue", border=True, align_center=True, border_thick="medium")
    qty_style = _xls_style(bold=True, fill_rgb="light_green", border=True, align_center=True)
    plain_style = _xls_style(border=True)
    code_style = _xls_style(border=True, num_format="@")
    qty_col_idx = keys.index("order_qty") if "order_qty" in keys else None
    code_col_idx = keys.index("product_code") if "product_code" in keys else None

    for c, key in enumerate(keys):
        ws.write(0, c, _EXPORT_COLUMN_MAP[key][0], header_style)

    for r, row in enumerate(rows, start=1):
        for c, key in enumerate(keys):
            value = _EXPORT_COLUMN_MAP[key][1](row)
            if c == qty_col_idx:
                ws.write(r, c, value, qty_style)
            elif c == code_col_idx:
                ws.write(r, c, value, code_style)
            else:
                ws.write(r, c, value, plain_style)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_order(store_name, supplier_code, supplier_name, mode, split_size, actor, columns=None, file_format="xlsx", order_no=None, product_codes=None, all_products=False, removed_product_codes=None):
    """Resolve the rows to export -> build Excel -> return.

    Two entry shapes, both from the Order Workspace:

    * By Supplier grid (product_codes is a list): the grid loads candidates
      UNassigned; the operator reviews, deletes unwanted rows, then exports.
      product_codes is exactly what's left in the grid. Export assigns only
      those to the supplier (status 0->1, scoped to orderqty>0) and includes
      only those -- so a deleted row is neither assigned nor exported, and the
      whole store is never silently closed out just because a supplier was
      selected.

    * Assigned view (product_codes is None): export simply reflects whatever
      is already Assigned (status=1) to this supplier; nothing is assigned.

    removed_product_codes is a SECOND, independent exclusion on top of
    product_codes (see schemas.ExportOrderRequest's docstring) -- subtracted
    from both the to-assign set and the final exported rows, even if
    `rows` (sourced from assigned_orders(), which returns every row already
    assigned to this supplier regardless of today's session) would otherwise
    have included one of them from an earlier, unrelated assignment."""
    removed = {_format_product_code(c) for c in (removed_product_codes or [])}
    if product_codes is not None:
        wanted = {_format_product_code(c) for c in product_codes} - removed
        # Never trust the client's code list to bypass store/orderqty>0 scoping:
        # re-resolve the legitimate open candidates server-side (the same set
        # the grid loaded from) and assign only the intersection of "still in
        # the grid" and "a real open candidate". In "Load all products" mode
        # the grid loaded every open orderable product, so re-resolve against
        # that set -- re-resolving against the supplier match would wrongly drop
        # the deliberately-added, unmatched products that are the whole point of
        # the toggle. Rows the operator already assigned by hand are status=1
        # (not returned by either source) -- they're picked up by the
        # assigned_orders fetch below as long as they're still in `wanted`.
        candidates = (repository.all_open_orderables(store_name) if all_products
                      else repository.orders_by_supplier(store_name, supplier_code, mode))
        to_assign = [r.get("ProductCode") for r in candidates
                     if _format_product_code(r.get("ProductCode")) in wanted]
        repository.bulk_assign_rows(store_name, supplier_code, supplier_name, to_assign, actor)
        rows = repository.assigned_orders(store_name, supplier_code)
        rows = [r for r in rows if _format_product_code(r.get("ProductCode")) in wanted]
    else:
        rows = repository.assigned_orders(store_name, supplier_code)
        if removed:
            rows = [r for r in rows if _format_product_code(r.get("ProductCode")) not in removed]
    rows = [r for r in rows if (r.get("OrderQty") or 0) > 0]
    if not rows:
        raise NoExportableRows("No assigned products with a positive order quantity to export for this supplier.")

    has_rack = mode == "stock"
    for r in rows:
        r["Category"] = _predict_category(r.get("SubLocation"), r.get("ProductName"), r.get("UnitDescription"))

    if has_rack:
        rows.sort(key=lambda r: (0 if (r.get("Rack") or "").strip() else 1, (r.get("Rack") or "").strip(), r.get("ProductName") or ""))
    else:
        rows.sort(key=lambda r: r.get("ProductName") or "")

    assigned_count = len(rows)

    # ddmmyyyy (owner request 2026-10-22, e.g. "22102026") -- was %d%m%y
    # ("221026"), which doesn't match the folder-name format the operator
    # wants (D:\Export Order\22102026\<order no>\*.xls).
    date_part = datetime.date.today().strftime("%d%m%Y")
    order_part = order_no if order_no else date_part
    base_name = _safe_file_name(f"{supplier_name} {date_part} {order_part}")

    try:
        split_size = int(split_size or 0)
    except (TypeError, ValueError):
        split_size = 0

    if 0 < split_size < len(rows):
        chunks = [rows[i:i + split_size] for i in range(0, len(rows), split_size)]
    else:
        chunks = [rows]

    custom = columns is not None
    file_format = file_format if file_format in ("xlsx", "xls", "csv") else "xls"
    ext = "csv" if (custom and file_format == "csv") else file_format if file_format in ("xlsx", "xls") else "xls"

    def build_one(chunk):
        if file_format == "xls":
            return _build_workbook_custom_xls(chunk, columns) if custom else _build_workbook_xls(chunk, has_rack)
        if not custom:
            return _build_workbook(chunk, has_rack)
        if file_format == "csv":
            return _build_csv_custom(chunk, columns)
        return _build_workbook_custom(chunk, columns)

    try:
        if len(chunks) == 1:
            content = build_one(chunks[0])
            filename = f"{base_name}.{ext}"
            media_type = "text/csv" if ext == "csv" else (XLS_MEDIA_TYPE if ext == "xls" else XLSX_MEDIA_TYPE)
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for idx, chunk in enumerate(chunks, start=1):
                    part_name = f"{base_name} Part {idx} of {len(chunks)}.{ext}"
                    zf.writestr(part_name, build_one(chunk))
            content = buf.getvalue()
            filename = f"{base_name}.zip"
            media_type = ZIP_MEDIA_TYPE
    except Exception as exc:
        logger.exception(
            "Order export: workbook build failed for store=%s supplier=%s (%s assigned rows)",
            store_name, supplier_code, assigned_count,
        )
        raise ExportGenerationFailed("Excel generation failed. No assignments were changed -- retry the export.") from exc

    return ExportResult(content, filename, media_type, assigned_count, supplier_name)
