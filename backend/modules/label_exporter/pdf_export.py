"""Label Exporter PDF export — tiles one box-card per assigned location onto
landscape A3 sheets.

Layout replicates the legacy VB6 Excel export (pRINTING.frm, Command10 /
"export column with 23" handler), verified against both the source and a
sample printout ("label sample.pdf") supplied for reference:

  - Each box is a 2-column x 5-row grid. Two equal-width product-name
    columns hold up to 7 product names, filled in the same zigzag order the
    VB6 code used: row0 L/R, row1 L/R, row2 L, row3 L, row4 L.
  - The location code (e.g. "W 1") is a single merged cell spanning the
    right column across rows 2-4 — a big bold label sitting in the middle
    of the box, exactly like the original stock-room labels.
  - Product names are capped at 18 characters, matching the legacy
    `Mid$(rs4.Fields(0), 1, 18)` truncation.
  - Every cell (product + label) gets a thin border; the outer card border
    is drawn heavier so boxes stand out when cut apart.

Text is placed with `page.insert_text` at a manually computed baseline
rather than `insert_textbox`: the latter refuses to draw anything at all
unless the box is ~1.68x the fontsize tall (an artifact of its own fit
check), which forced font sizes far smaller than the reference printout's
actual 13.6pt (names) / 48pt (codes). Direct glyph placement has no such
floor, gives exact left-alignment for names and exact centering for the
location code, and each string is shrunk (in 0.5pt steps down to a floor)
only if it would otherwise overflow its cell width — e.g. long SYP-bucket
codes like "SYPA012" or unusually long product names.

Page is landscape A3, filled column-major (straight down one group of
boxes before moving to the next), with as many groups across as fit at a
sane minimum card width (falls back from 4 to 3 if the sheet is too
narrow) — margins are recomputed so the grid is centered left-right and
top-bottom rather than packed into one corner.

See label-exporter-legacy-vb6-rules / label-exporter-redesign-progress memory.
"""
import re

import fitz

PT_PER_IN = 72
CARD_HEIGHT_IN = 1.15
MARGIN_IN = 0.3
GAP_IN = 0.15
MAX_PRODUCTS_PER_CARD = 7
NAME_MAX_CHARS = 18

# Each product-name column is sized to Excel column-width "25" (the legacy
# VB6 export's Columns(n).ColumnWidth = 25), converted via Excel's own
# width->pixel formula (px = width*7 + 5, at the 96dpi basis that formula
# assumes) and then to points. A card is two of these columns side by side.
_EXCEL_COL_WIDTH_UNITS = 25
_NAME_COL_W = (_EXCEL_COL_WIDTH_UNITS * 7 + 5) / 96 * PT_PER_IN
_CARD_W = _NAME_COL_W * 2

_CARD_H = CARD_HEIGHT_IN * PT_PER_IN
_MARGIN = MARGIN_IN * PT_PER_IN
_GAP = GAP_IN * PT_PER_IN
_NUM_ROWS = 5
_ROW_H = _CARD_H / _NUM_ROWS

# (row, col) for each of the 7 product slots, col 0 = left, col 1 = right.
# Rows 2-4 of the right column are reserved for the merged location label.
_SLOT_POSITIONS = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (3, 0), (4, 0)]

_FONT_NAME = "hebo"
_FONT = fitz.Font(_FONT_NAME)
_NAME_COLOR = (0.0, 0.2, 0.0)       # dark green, sampled from the reference printout
_LOC_COLOR = (0.0, 0.2, 0.0)        # same dark green — matches the reference printout exactly
_NAME_FONT_MAX = 11.0
_NAME_FONT_MIN = 6.0
# The reference printout uses 13.6pt names / 48pt codes — a fixed ~3.53x
# ratio. Scaling off our actual name size (not a hardcoded number) keeps the
# code proportionate to whatever the name font ends up being, instead of
# looking oversized against a smaller name font.
_REFERENCE_NAME_FONT = 13.6
_REFERENCE_LOC_FONT = 48.0
_LOC_FONT_MAX = round(_NAME_FONT_MAX * (_REFERENCE_LOC_FONT / _REFERENCE_NAME_FONT), 1)
_LOC_FONT_MIN = 16.0

# Legacy (pRINTING.frm) stored letter and box-number in separate `let`/`locn`
# columns and built the label with `letter + Str(number)` — and Str() never
# zero-pads, so legacy labels read "W 1", not "W 001". Our schema only has
# one combined `assigned_sublocation` field ("A001"), so there's no separate
# number column to read un-padded — instead this regex splits the stored
# string back into (letters, digits) at render time and re-joins without the
# padding, purely for display. The stored/sorted value is untouched.
_LOC_SPLIT_RE = re.compile(r"^([A-Za-z]+)0*(\d+)$")


def _short_location(location: str) -> str:
    if not location:
        return location
    match = _LOC_SPLIT_RE.match(location.strip())
    if not match:
        return location
    letters, digits = match.groups()
    return f"{letters}{int(digits)}"
_CELL_PAD_X = 4.0
_OUTER_BORDER_W = 1.5   # doubled from the original 0.75
_INNER_BORDER_W = 0.4


def _group_by_location(rows):
    """Rows already arrive ordered by (location, name) from
    repository.get_label_queue. Split into per-box groups, capping each at
    MAX_PRODUCTS_PER_CARD so an over-full box (shouldn't happen, but data can
    drift) spills onto a continuation card rather than overflowing the box."""
    groups = []
    current = None
    last_location = object()
    for row in rows:
        location = row.get("location") or ""
        if location != last_location or (current and len(current["items"]) >= MAX_PRODUCTS_PER_CARD):
            current = {"location": location, "items": []}
            groups.append(current)
            last_location = location
        current["items"].append(row)
    return groups


# Trailing dosage-form words and pack-size counts, stripped unconditionally
# (not gated on the row's own unit_description — that field turns out to be
# unreliable: plenty of TAB-unit rows still carry a "CAP"/"CAPS" name suffix
# from before the unit was corrected). This whitelist is deliberately tiny
# and pharma-specific (unlike the full 300+ value unit_description list,
# which includes generic English words like "PACK"/"BOX"/"CARD" that would
# corrupt real names) — TAB/CAP variants and a bracket tag ("[VET]") or
# pack-count ("60'S"/"10S") are never meaningful trailing content on their
# own. The (^|\s) requirement matters: without it this would also match
# inside a fused word like "PEDTABS" and wrongly chop it down to "PED".
# The apostrophe class includes a backtick: some master data uses ` instead
# of ' for pack counts ("ALPHADOL 0.25MG 10`S"), and without it the pattern
# doesn't match at all, so the count survives stripping only to get cut in
# half by the 18-char truncation into a bare, meaningless "10".
_TRAILING_NOISE_RE = re.compile(
    r"(^|\s)(\[[A-Za-z]+\]|TAB(?:LET)?S?|CAP(?:SULE)?S?|CA|\d+['’`]?S)$",
    re.IGNORECASE,
)


def _strip_trailing_noise(name):
    while True:
        match = _TRAILING_NOISE_RE.search(name)
        if not match:
            return name.strip()
        name = name[: match.start()].rstrip()


def _display_name(item):
    # The unit type used to be appended here too, but every box is already
    # scoped to one unit (see AssignLocationsModal — assignment runs per
    # unit), so it's redundant on every row for every store and every letter.
    # Stripping trailing noise BEFORE truncating to NAME_MAX_CHARS matters —
    # doing it after let a 19-char name like "ALAMIN -M FORTE CAP" get cut
    # mid-word into "...CA" instead of being fully removed first.
    # Master data has plenty of doubled/trailing internal spaces ("ADDKAY
    # TAB" -> stored as "ADDKAY  TAB", "ARK  AP") and hyphens used as a
    # word-join ("ACEFLAM-P", "ADBLOCK- AT") — replace hyphens with a space
    # and collapse any run of whitespace to a single space, for every store.
    name = (item.get("product_name") or "").replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    name = _strip_trailing_noise(name)
    return name[:NAME_MAX_CHARS]


def _fit_fontsize(text, max_size, min_size, avail_width):
    size = max_size
    while size > min_size:
        if fitz.get_text_length(text, fontname=_FONT_NAME, fontsize=size) <= avail_width:
            return size
        size -= 0.5
    return min_size


def _draw_text(page, cell, text, max_size, min_size, color, align):
    """align: 'left' (product names) or 'center' (location code). Vertical
    centering always uses the font's real ascender/descender so the glyph
    box — not an arbitrary line-height guess — is centered in the cell."""
    if not text:
        return
    avail_w = cell.width - 2 * _CELL_PAD_X
    fontsize = _fit_fontsize(text, max_size, min_size, avail_w)
    glyph_h = (_FONT.ascender - _FONT.descender) * fontsize
    top_pad = max(0.0, (cell.height - glyph_h) / 2)
    baseline_y = cell.y0 + top_pad + _FONT.ascender * fontsize
    if align == "center":
        text_w = fitz.get_text_length(text, fontname=_FONT_NAME, fontsize=fontsize)
        x = cell.x0 + (cell.width - text_w) / 2
    else:
        x = cell.x0 + _CELL_PAD_X
    page.insert_text(fitz.Point(x, baseline_y), text, fontsize=fontsize, fontname=_FONT_NAME, color=color)


def _draw_card(page, x0, y0, card_w, group):
    col_w = card_w / 2
    outer = fitz.Rect(x0, y0, x0 + card_w, y0 + _CARD_H)
    page.draw_rect(outer, color=(0, 0, 0), width=_OUTER_BORDER_W)

    col_x = [x0, x0 + col_w, x0 + card_w]
    row_y = [y0 + i * _ROW_H for i in range(_NUM_ROWS + 1)]

    items = group["items"]
    for idx in range(MAX_PRODUCTS_PER_CARD):
        row, col = _SLOT_POSITIONS[idx]
        cell = fitz.Rect(col_x[col], row_y[row], col_x[col + 1], row_y[row + 1])
        page.draw_rect(cell, color=(0, 0, 0), width=_INNER_BORDER_W)
        if idx < len(items):
            _draw_text(page, cell, _display_name(items[idx]), _NAME_FONT_MAX, _NAME_FONT_MIN, _NAME_COLOR, "left")

    label_rect = fitz.Rect(col_x[1], row_y[2], col_x[2], row_y[_NUM_ROWS])
    page.draw_rect(label_rect, color=(0, 0, 0), width=_INNER_BORDER_W)
    _draw_text(page, label_rect, _short_location(group["location"]) or "-", _LOC_FONT_MAX, _LOC_FONT_MIN, _LOC_COLOR, "center")


def build_label_queue_pdf(rows: list[dict]) -> bytes:
    """One box-card per assigned location, tiled top-to-bottom within a
    group of box-columns, then left-to-right across groups (centered on the
    sheet), across as many landscape A3 pages as needed."""
    groups = _group_by_location(rows)
    portrait_w, portrait_h = fitz.paper_size("a3")
    page_w, page_h = portrait_h, portrait_w  # landscape

    card_w = _CARD_W
    cols = max(1, int((page_w - 2 * _MARGIN + _GAP) // (card_w + _GAP)))

    rows_per_page = max(1, int((page_h - 2 * _MARGIN + _GAP) // (_CARD_H + _GAP)))
    per_page = cols * rows_per_page

    used_w = cols * card_w + (cols - 1) * _GAP
    used_h = rows_per_page * _CARD_H + (rows_per_page - 1) * _GAP
    margin_x = (page_w - used_w) / 2
    margin_y = (page_h - used_h) / 2

    doc = fitz.open()
    page = None
    for i, group in enumerate(groups):
        pos = i % per_page
        if pos == 0:
            page = doc.new_page(width=page_w, height=page_h)
        col = pos // rows_per_page
        row_i = pos % rows_per_page
        x0 = margin_x + col * (card_w + _GAP)
        y0 = margin_y + row_i * (_CARD_H + _GAP)
        _draw_card(page, x0, y0, card_w, group)

    if page is None:
        page = doc.new_page(width=page_w, height=page_h)
        page.insert_textbox(
            fitz.Rect(_MARGIN, _MARGIN, page_w - _MARGIN, _MARGIN + 24),
            "No labels in queue.", fontsize=12, fontname="helv",
        )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
