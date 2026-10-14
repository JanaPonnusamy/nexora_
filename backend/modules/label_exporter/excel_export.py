"""Label Exporter Excel export — one styled worksheet per "Export to Excel"
click, scoped to the currently loaded shelf letter. Mirrors the styling
conventions used by modules/time_report/excel_export.py (openpyxl, bold
header row, thin borders, autosized columns)."""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

BOLD = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")
THIN = Side(style="thin", color="BBBBBB")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(bold=True, color="FFFFFF")

_COLUMNS = [
    ("product_code", "Code", 14),
    ("product_name", "Product", 40),
    ("unit_description", "Old Unit", 12),
    ("corrected_unit", "New Unit", 12),
    ("sale_unit", "Sale Unit", 10),
    ("current_sublocation", "Old Loc", 12),
    ("assigned_sublocation", "New Loc", 12),
    ("total_stock", "Stock", 10),
    ("purchase_days", "LPD", 8),
    ("sale_days", "LSD", 8),
    ("include_label", "Review", 10),
]


def build_letter_xlsx(rows: list[dict], letter: str) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = (letter or "Letter")[:31] or "Letter"
    ncol = len(_COLUMNS)

    title = f"Label Exporter — Letter {letter}" if letter else "Label Exporter — All letters"
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    t = ws.cell(row=1, column=1, value=title)
    t.font = BOLD
    t.alignment = CENTER

    header_row = 2
    for col, (_, label, _) in enumerate(_COLUMNS, 1):
        c = ws.cell(row=header_row, column=col, value=label)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = CENTER
        c.border = BORDER

    r = header_row + 1
    for row in rows:
        for col, (key, _, _) in enumerate(_COLUMNS, 1):
            value = row.get(key)
            if key == "include_label":
                value = value or "N/A"
            c = ws.cell(row=r, column=col, value=value)
            c.border = BORDER
            c.alignment = LEFT if key in ("product_name",) else CENTER
        r += 1

    for col, (_, _, width) in enumerate(_COLUMNS, 1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = f"A{header_row + 1}"
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(ncol)}{header_row}"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
