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
# Every builder is split into a *layout* (headers + value table) and a
# *writer* (xlsx / xls / csv / png), so the files and the images render the
# exact same table.
# --------------------------------------------------------------------------

def _format_product_code(value):
    """ordermanagement.productcode round-trips through pyodbc as a Python
    float (e.g. 9810.0), not an int, even though it's always a whole number.
    str(9810.0) == "9810.0" -- matching on that string would silently fail
    with a bogus ".0" suffix. Only numeric types get this treatment -- a
    string value is left exactly as-is (never round-tripped through float()),
    so a genuine text code with leading zeros is never touched."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value) == int(value):
            return str(int(value))
    return str(value)


def _product_code_value(value):
    """ProductCode as written into the sheet: a real NUMBER (owner request
    2026-10-24 -- was a "@" text cell, which Excel flags with the green
    number-stored-as-text triangle and left-aligns). Anything that isn't a
    plain whole number (letters, a leading zero) stays text so it's never
    mangled."""
    code = _format_product_code(value)
    if code.isdigit() and (code == "0" or not code.startswith("0")):
        return int(code)
    return code


# --------------------------------------------------------------------------
# Cell styling -- the legacy VB.NET colour rules (Form1.vb ~lines 4332-4366:
# S.No. bold/centred/LightYellow, OrderQty bold/centred/LightGreen, SaleUnit
# grey centred, MRP grey "0.00") on a cleaner sheet (owner request
# 2026-10-24): Calibri 12 everywhere, legacy bold centred header with NO
# fill, thin inner borders with a THICK border around the used range, 17pt
# rows, ProductCode numeric + right-aligned, roomier column widths. Styling is
# keyed off the header label so every builder (fixed, custom, pending; xlsx,
# xls and png) renders identically.
# --------------------------------------------------------------------------

_VB_LIGHT_YELLOW = "FFFFE0"
_VB_LIGHT_GREEN = "90EE90"
_VB_GRAY = "808080"
_FONT_NAME = "Calibri"
_FONT_SIZE = 12
_ROW_HEIGHT_PT = 17  # owner ruling 2026-10-24: exactly 17pt
_PRODUCTS_PER_IMAGE = 20


def _cell_spec(label, header=False):
    """bold / fill / font colour / horizontal align / number format for one
    cell. align None = Excel's General (numbers right, text left)."""
    spec = {"bold": False, "fill": None, "color": "000000", "align": None, "num_format": None}
    label = str(label)
    if header:
        spec.update(bold=True, align="center")
    elif label == "S.No.":
        spec.update(bold=True, fill=_VB_LIGHT_YELLOW, align="center")
    elif label == "OrderQty":
        spec.update(bold=True, fill=_VB_LIGHT_GREEN, align="center")
    elif label == "SaleUnit":
        spec.update(color=_VB_GRAY, align="center")
    elif label == "MRP":
        spec.update(color=_VB_GRAY, align="right", num_format="0.00")
    elif label.lower() == "productcode":
        spec.update(align="right", num_format="0")
    return spec


def _column_widths(headers, table):
    """Character widths, sized for Calibri 12 (wider than Excel's 11pt
    default the old auto-fit assumed, which is what made it look cramped)."""
    widths = []
    for c, h in enumerate(headers):
        longest = max([len(str(h))] + [len(str(row[c])) for row in table if row[c] is not None])
        widths.append(min(longest, 45) * 1.15 + 4)
    return widths


def _write_xlsx(headers, table):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)
    for values in table:
        ws.append(values)

    thin = Side(style="thin", color="000000")
    thick = Side(style="thick", color="000000")
    last_row, last_col = len(table) + 1, len(headers)
    specs = [_cell_spec(h) for h in headers]
    for row in ws.iter_rows(min_row=1, max_row=last_row, max_col=last_col):
        for cell in row:
            r, c = cell.row, cell.column
            spec = _cell_spec(headers[c - 1], header=True) if r == 1 else specs[c - 1]
            cell.border = Border(
                left=thick if c == 1 else thin, right=thick if c == last_col else thin,
                top=thick if r == 1 else thin, bottom=thick if r == last_row else thin,
            )
            cell.font = Font(name=_FONT_NAME, size=_FONT_SIZE, bold=spec["bold"], color=spec["color"])
            cell.alignment = Alignment(horizontal=spec["align"], vertical="center")
            if spec["fill"]:
                cell.fill = PatternFill("solid", fgColor=spec["fill"])
            if spec["num_format"]:
                cell.number_format = spec["num_format"]
    for r in range(1, last_row + 1):
        ws.row_dimensions[r].height = _ROW_HEIGHT_PT
    for c, w in enumerate(_column_widths(headers, table), start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A2"

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

# BIFF fills come from a fixed 56-colour palette whose light_yellow/
# light_green are only near the VB.NET colours (FFFF99/CCFFCC) -- each
# workbook re-points those two slots to the exact legacy RGB.
_XLS_FILL_NAMES = {_VB_LIGHT_YELLOW: "light_yellow", _VB_LIGHT_GREEN: "light_green"}
_XLS_COLOUR_NAMES = {"000000": "black", _VB_GRAY: "gray50"}
_XLS_ALIGN = {"center": "center", "right": "right", "left": "left"}


def _xls_style(spec, left, right, top, bottom):
    """xlwt easyxf for one cell from a _cell_spec; the four flags pick a
    thick edge on the outside of the used range, thin inside."""
    import xlwt
    edge = lambda outer: "thick" if outer else "thin"
    parts = [
        f"borders: left {edge(left)}, right {edge(right)}, top {edge(top)}, bottom {edge(bottom)}",
        f"font: name {_FONT_NAME}, height {_FONT_SIZE * 20}, colour {_XLS_COLOUR_NAMES[spec['color']]}"
        + (", bold on" if spec["bold"] else ""),
        "align: vert centre" + (f", horiz {_XLS_ALIGN[spec['align']]}" if spec["align"] else ""),
    ]
    if spec["fill"]:
        parts.append(f"pattern: pattern solid, fore_colour {_XLS_FILL_NAMES[spec['fill']]}")
    xf = xlwt.easyxf("; ".join(parts))
    if spec["num_format"]:
        xf.num_format_str = spec["num_format"]
    return xf


def _write_xls(headers, table):
    """headers: labels; table: list of value lists (already in header order)."""
    import xlwt
    wb = xlwt.Workbook()
    for rgb, name in _XLS_FILL_NAMES.items():
        wb.set_colour_RGB(xlwt.Style.colour_map[name], *(int(rgb[i:i + 2], 16) for i in (0, 2, 4)))
    ws = wb.add_sheet("Sheet1")

    last_row, last_col = len(table), len(headers) - 1
    specs = [_cell_spec(h) for h in headers]
    header_spec = _cell_spec(None, header=True)
    styles = {}  # BIFF caps a workbook at ~4k XFs -- one per distinct combo

    def style(r, c):
        key = (r == 0, c, r == last_row)
        if key not in styles:
            styles[key] = _xls_style(header_spec if r == 0 else specs[c],
                                     c == 0, c == last_col, r == 0, r == last_row)
        return styles[key]

    for c, label in enumerate(headers):
        ws.write(0, c, label, style(0, c))
    for r, values in enumerate(table, start=1):
        for c, value in enumerate(values):
            ws.write(r, c, value, style(r, c))
    for r in range(last_row + 1):
        ws.row(r).height_mismatch = True
        ws.row(r).height = _ROW_HEIGHT_PT * 20
    for c, w in enumerate(_column_widths(headers, table)):
        ws.col(c).width = int(256 * w)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_csv(headers, table):
    import csv
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(table)
    return buf.getvalue().encode("utf-8-sig")  # BOM so Excel opens non-ASCII cleanly


_WRITERS = {"xlsx": _write_xlsx, "xls": _write_xls, "csv": _write_csv}


# --------------------------------------------------------------------------
# Image export (owner request 2026-10-24) -- the same table the sheet holds,
# rendered to PNGs of 20 products each ("<base> Part 1.png", "Part 2", ...).
# Every image repeats the header row, the sheet's fills/borders, and keeps
# a white padding margin outside the thick outer border. Column widths are
# measured over the WHOLE table so every part lines up identically.
# --------------------------------------------------------------------------

# Dark theme matching the Stock Client's dark palette (styles.css
# :root[data-theme="dark"]) and its UI font (Segoe UI), so a shared image reads
# like the Order Workspace grid. The .xlsx/.xls/.csv sheet keeps its light
# legacy colours (_cell_spec) -- only the PNGs are dark.
_IMG_CANVAS = "0a0f17"       # --nx-canvas (padding outside the table)
_IMG_ROW = "111823"          # --nx-surface
_IMG_ROW_ALT = "151e2b"      # zebra stripe between surface and surface-raised
_IMG_HEADER = "17202d"       # --nx-surface-raised
_IMG_RULE = "32404f"         # --nx-rule-strong
_IMG_OUTER = "4f8df7"        # --nx-accent
_IMG_TEXT = "e7edf5"         # --nx-text
_IMG_TEXT_SOFT = "b6c2d2"    # --nx-text-soft
_IMG_TEXT_MUTED = "8494a8"   # --nx-text-muted


def _image_cell_spec(label, header=False):
    """_cell_spec's per-column emphasis, recoloured for the dark image."""
    spec = {"bold": False, "fill": None, "color": _IMG_TEXT, "align": None}
    label = str(label)
    if header:
        spec.update(bold=True, fill=_IMG_HEADER, color=_IMG_TEXT_SOFT, align="center")
    elif label == "S.No.":
        spec.update(color=_IMG_TEXT_MUTED, align="center")
    elif label == "OrderQty":
        spec.update(bold=True, fill="0c2a22", color="4ade94", align="center")  # success-sunk / -ink
    elif label in ("SaleUnit", "MRP"):
        spec.update(color=_IMG_TEXT_SOFT, align="center" if label == "SaleUnit" else "right")
    elif label.lower() == "productcode":
        spec.update(color=_IMG_TEXT_SOFT, align="right")
    elif label == "ProductName":
        spec.update(bold=True)
    return spec


def _image_font(px, bold=False):
    from PIL import ImageFont
    names = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold
             else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    for name in names:
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _image_text(value, label):
    if value is None:
        return ""
    if str(label) == "MRP" and isinstance(value, (int, float)):
        return f"{value:.2f}"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def _render_images(headers, table, base_name, per_image=_PRODUCTS_PER_IMAGE):
    """[(filename, png bytes), ...] -- one PNG per `per_image` rows."""
    from PIL import Image, ImageDraw

    rgb = lambda h: tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    font, font_bold = _image_font(17), _image_font(17, bold=True)
    pad, cell_pad, row_h, thick = 28, 12, 34, 2
    specs = [_image_cell_spec(h) for h in headers]
    header_spec = _image_cell_spec(None, header=True)
    texts = [[_image_text(v, headers[c]) for c, v in enumerate(row)] for row in table]

    scratch = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    col_w = []
    for c, h in enumerate(headers):
        widest = max([scratch.textlength(str(h), font=font_bold)]
                     + [scratch.textlength(row[c], font=font_bold if specs[c]["bold"] else font) for row in texts])
        col_w.append(int(widest) + cell_pad * 2)
    table_w = sum(col_w)

    def draw_row(draw, y, values, row_specs, raw_values, row_fill):
        x = pad
        for c, text in enumerate(values):
            spec = row_specs[c]
            box = [x, y, x + col_w[c], y + row_h]
            draw.rectangle(box, fill=rgb(spec["fill"] or row_fill), outline=rgb(_IMG_RULE), width=1)
            f = font_bold if spec["bold"] else font
            tw = draw.textlength(text, font=f)
            align = spec["align"] or ("right" if isinstance(raw_values[c], (int, float)) else "left")
            tx = (x + (col_w[c] - tw) / 2 if align == "center"
                  else x + col_w[c] - cell_pad - tw if align == "right" else x + cell_pad)
            draw.text((tx, y + row_h / 2), text, font=f, fill=rgb(spec["color"]), anchor="lm")
            x += col_w[c]

    images = []
    for part, start in enumerate(range(0, len(table), per_image), start=1):
        chunk = range(start, min(start + per_image, len(table)))
        table_h = row_h * (len(chunk) + 1)
        img = Image.new("RGB", (table_w + pad * 2, table_h + pad * 2), rgb(_IMG_CANVAS))
        draw = ImageDraw.Draw(img)
        draw_row(draw, pad, [str(h) for h in headers], [header_spec] * len(headers), headers, _IMG_HEADER)
        for n, i in enumerate(chunk, start=1):
            draw_row(draw, pad + n * row_h, texts[i], specs, table[i], _IMG_ROW if n % 2 else _IMG_ROW_ALT)
        draw.rectangle([pad - 1, pad - 1, pad + table_w + 1, pad + table_h + 1], outline=rgb(_IMG_OUTER), width=thick)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        images.append((f"{base_name} Part {part}.png", buf.getvalue()))
    return images


# --------------------------------------------------------------------------
# Layouts. Legacy fixed layout (no `columns`): S.No., ProductName, OrderQty,
# SaleUnit, MRP, ProductCode, Discount, Category, SubLocation[, Rack].
# --------------------------------------------------------------------------

def _layout_fixed(rows, has_rack):
    headers = ["S.No.", "ProductName", "OrderQty", "SaleUnit", "MRP", "ProductCode", "Discount", "Category", "SubLocation"]
    if has_rack:
        headers.append("Rack")
    table = []
    for i, row in enumerate(rows, start=1):
        values = [
            i, row.get("ProductName") or "", row.get("OrderQty") or 0, row.get("SaleUnit") or "",
            row.get("MRP") or 0, _product_code_value(row.get("ProductCode")),
            row.get("Discount") if has_rack else "", row.get("Category") or "", row.get("SubLocation") or "",
        ]
        if has_rack:
            values.append(row.get("Rack") or "")
        table.append(values)
    return headers, table


# --------------------------------------------------------------------------
# Configurable export — operator-chosen column subset + xlsx/csv, used when
# the request supplies `columns`/`file_format`. ProductCode/ProductName/
# OrderQty are always included regardless of selection (enforced here, not
# just client-side, since this is a public API contract). Keeps the legacy
# fixed layout above completely untouched for existing callers that omit
# `columns` — this is strictly additive.
# --------------------------------------------------------------------------

_EXPORT_COLUMN_MAP = {
    "product_code": ("ProductCode", lambda r: _product_code_value(r.get("ProductCode"))),
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


def _layout_generic(rows, keys, column_map):
    """Operator-chosen columns in the given key order, against any column
    map (By Supplier's _EXPORT_COLUMN_MAP or Pending's _PENDING_COLUMN_MAP)."""
    return ([column_map[k][0] for k in keys],
            [[column_map[k][1](row) for k in keys] for row in rows])


# Legacy VB export layout (Form1.ExportSelectedColumnsFromGrid): S.No. first,
# then ProductName, OrderQty, SaleUnit, MRP, Productcode, Discound (sic),
# Category, SubLocation, Rack -- header spellings copied verbatim because the
# supplier-side consumers of these sheets were built against the VB output.
# Used for the custom .xls export.
_VB_COLUMN_ORDER = ("product_name", "order_qty", "sale_unit", "mrp", "product_code",
                    "discount", "category", "sub_location", "rack")
_VB_HEADER = {"product_code": "Productcode", "discount": "Discound"}


def _layout_custom_vb(rows, columns):
    chosen = set(_resolve_columns(columns))
    keys = [k for k in _VB_COLUMN_ORDER if k in chosen]
    headers = ["S.No."] + [_VB_HEADER.get(k, _EXPORT_COLUMN_MAP[k][0]) for k in keys]
    table = [[i] + [_EXPORT_COLUMN_MAP[k][1](row) for k in keys] for i, row in enumerate(rows, start=1)]
    return headers, table


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
    "product_code": ("ProductCode", lambda r: _product_code_value(r.get("ProductCode"))),
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
    same PascalCase keys the column maps already expect, so this reuses the
    shared layout/writers instead of forking a Pending-only workbook."""
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


def _package(base_name, ext, chunks, layout, images):
    """Build the files for every chunk (+ optional PNGs over the full row
    set) -> (content, filename, media_type). One plain file when that's all
    there is; otherwise a .zip the desktop client unpacks into the order
    folder (split "Part n of m" files and/or the "Part n" images)."""
    writer = _WRITERS[ext]
    files = []
    if len(chunks) == 1:
        files.append((f"{base_name}.{ext}", writer(*layout(chunks[0]))))
    else:
        for idx, chunk in enumerate(chunks, start=1):
            files.append((f"{base_name} Part {idx} of {len(chunks)}.{ext}", writer(*layout(chunk))))
    if images:
        all_rows = [r for chunk in chunks for r in chunk]
        files.extend(_render_images(*layout(all_rows), base_name))

    if len(files) == 1:
        media_type = "text/csv" if ext == "csv" else (XLS_MEDIA_TYPE if ext == "xls" else XLSX_MEDIA_TYPE)
        return files[0][1], files[0][0], media_type
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    return buf.getvalue(), f"{base_name}.zip", ZIP_MEDIA_TYPE


def export_pending_order(store_name, split_size, columns=None, file_format="xlsx", order_no=None, images=False):
    rows = [_normalize_pending_row(r) for r in repository.pending_order_rows(store_name)]
    rows = [r for r in rows if (r.get("OrderQty") or 0) > 0]
    if not rows:
        raise NoExportableRows("No pending products with a positive order quantity to export.")

    rows.sort(key=lambda r: r.get("ProductName") or "")
    pending_count = len(rows)

    date_part = datetime.date.today().strftime("%d%m%Y")  # ddmmyyyy -- see export_order
    order_part = order_no if order_no else date_part
    base_name = _safe_file_name(f"Pending {date_part} {order_part}")

    # Rows-per-file split (legacy VB "split size"): the desktop client unpacks
    # the resulting .zip into separate "Part n of m" files in the order folder.
    try:
        split_size = int(split_size or 0)
    except (TypeError, ValueError):
        split_size = 0

    if 0 < split_size < len(rows):
        chunks = [rows[i:i + split_size] for i in range(0, len(rows), split_size)]
    else:
        chunks = [rows]

    keys = _resolve_pending_columns(columns)
    ext = file_format if file_format in ("xlsx", "xls", "csv") else "xls"

    try:
        content, filename, media_type = _package(
            base_name, ext, chunks, lambda chunk: _layout_generic(chunk, keys, _PENDING_COLUMN_MAP), images)
    except Exception as exc:
        logger.exception(
            "Pending order export: workbook build failed for store=%s (%s rows)",
            store_name, pending_count,
        )
        raise ExportGenerationFailed("Excel generation failed. No data was changed -- retry the export.") from exc

    return ExportResult(content, filename, media_type, pending_count, "Pending")


def export_order(store_name, supplier_code, supplier_name, mode, split_size, actor, columns=None, file_format="xlsx", order_no=None, product_codes=None, all_products=False, images=False):
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

    The grid is the single source of truth: no separate "removed" list is kept.
    A product not in product_codes is neither assigned nor exported."""
    if product_codes is not None:
        wanted = {_format_product_code(c) for c in product_codes}
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
    # Legacy VB name: "<supplier> <store name>   <ddMMyyyy>" (3 spaces).
    base_name = _safe_file_name(f"{supplier_name} {store_name}   {date_part}")

    # Rows-per-file split (legacy VB "split size"): the desktop client unpacks
    # the resulting .zip into separate "Part n of m" files in the order folder.
    try:
        split_size = int(split_size or 0)
    except (TypeError, ValueError):
        split_size = 0

    if 0 < split_size < len(rows):
        chunks = [rows[i:i + split_size] for i in range(0, len(rows), split_size)]
    else:
        chunks = [rows]

    ext = file_format if file_format in ("xlsx", "xls", "csv") else "xls"
    if columns is None:
        layout = lambda chunk: _layout_fixed(chunk, has_rack)
    elif ext == "xls":
        layout = lambda chunk: _layout_custom_vb(chunk, columns)
    else:
        layout = lambda chunk: _layout_generic(chunk, _resolve_columns(columns), _EXPORT_COLUMN_MAP)

    try:
        content, filename, media_type = _package(base_name, ext, chunks, layout, images)
    except Exception as exc:
        logger.exception(
            "Order export: workbook build failed for store=%s supplier=%s (%s assigned rows)",
            store_name, supplier_code, assigned_count,
        )
        raise ExportGenerationFailed("Excel generation failed. No assignments were changed -- retry the export.") from exc

    return ExportResult(content, filename, media_type, assigned_count, supplier_name)
