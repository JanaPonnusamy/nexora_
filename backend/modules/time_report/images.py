"""Render department (store) daily reports as PNG images using Pillow.

Ported unchanged from the standalone COSEC Flask app's images.py. Style
mirrors the reference report: green department title bar, a period line
(dd-mm-yyyy), 8 raw punch columns, smooth light row colours with black text,
and full cell borders.

- department_image(dept, data)        -> BytesIO of one store's PNG
- all_departments_zip(data)           -> BytesIO zip of every store's PNG
"""
import io
import zipfile

from PIL import Image, ImageDraw, ImageFont

from modules.time_report import config

NAME_MAX = 30          # max characters shown for a name
N_PUNCH = 8            # punch columns shown (matches reference report)

# Column layout: (header, width).  Punch columns are deliberately narrow.
COL_ID = ("ID", 56)
COL_NAME = ("Name", 215)
COL_PUNCH_W = 56
COL_WORK = ("Hrs", 64)
# Trailing month-to-date columns (see service._month_to_date_counts).
COL_MTD = [("MP Days", 66), ("<8:30", 56), ("<8:00", 56)]

ROW_H = 26
TITLE_H = 30
PERIOD_H = 26
HEAD_H = 24
PAD = 14
LEGEND_H = 26


def _font(size, bold=False):
    names = (["arialbd.ttf", "segoeuib.ttf"] if bold else ["arial.ttf", "segoeui.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rgb(hex_):
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))


def _text(draw, box, txt, font, color, align="center"):
    x0, y0, x1, y1 = box
    txt = "" if txt is None else str(txt)
    tw = draw.textlength(txt, font=font)
    th = font.size
    ty = y0 + (y1 - y0 - th) / 2 - 1
    tx = x0 + 6 if align == "left" else x0 + (x1 - x0 - tw) / 2
    draw.text((tx, ty), txt, font=font, fill=color)


def _columns():
    cols = [COL_ID, COL_NAME]
    cols += [(str(i + 1), COL_PUNCH_W) for i in range(N_PUNCH)]
    cols.append(COL_WORK)
    cols += COL_MTD
    return cols


def department_image(dept, data) -> io.BytesIO:
    f_title = _font(15, bold=True)
    f_period = _font(13, bold=True)
    f_head = _font(12, bold=True)
    f_cell = _font(12)
    f_small = _font(11)

    cols = _columns()
    total_w = sum(w for _, w in cols)
    width = total_w + PAD * 2
    n = len(dept["rows"])
    height = (PAD * 2 + TITLE_H + PERIOD_H + HEAD_H + n * ROW_H
              + ROW_H + LEGEND_H + 6)

    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    grid = _rgb("808080")
    black = _rgb(config.BLACK)
    head_bg = _rgb(config.COLOR_HEADER)
    sub_bg = _rgb(config.COLOR_SUBHEAD)

    x0 = PAD
    y = PAD

    # 1. title bar (department / store) - green, black text
    d.rectangle([x0, y, x0 + total_w, y + TITLE_H], fill=head_bg, outline=grid)
    _text(d, (x0, y, x0 + total_w, y + TITLE_H), dept["name"], f_title, black)
    y += TITLE_H

    # 2. period line - white, black text
    d.rectangle([x0, y, x0 + total_w, y + PERIOD_H], fill=(255, 255, 255), outline=grid)
    _text(d, (x0, y, x0 + total_w, y + PERIOD_H), data["period"], f_period, black)
    y += PERIOD_H

    # 3. column header - light grey
    cx = x0
    for header, w in cols:
        d.rectangle([cx, y, cx + w, y + HEAD_H], fill=sub_bg, outline=grid)
        _text(d, (cx, y, cx + w, y + HEAD_H), header, f_head, black)
        cx += w
    y += HEAD_H

    # 4. data rows
    for row in dept["rows"]:
        bg = _rgb(row["status_hex"])
        punches = (row["punches"] + [""] * N_PUNCH)[:N_PUNCH]
        name = row["name"][:NAME_MAX]
        mtd = [row.get("mp_month", 0) or 0, row.get("below_830", 0) or 0,
               row.get("below_800", 0) or 0]
        values = ([row["user_id"], name] + punches + [row["work_hm"]]
                  + [v if v else "" for v in mtd])
        cx = x0
        for (header, w), val in zip(cols, values):
            d.rectangle([cx, y, cx + w, y + ROW_H], fill=bg, outline=grid)
            _text(d, (cx, y, cx + w, y + ROW_H), val, f_cell, black,
                  align="left" if header == "Name" else "center")
            cx += w
        y += ROW_H

    # 5. totals row
    t = dept["totals"]
    d.rectangle([x0, y, x0 + total_w, y + ROW_H], fill=_rgb(config.COLOR_TOTAL),
                outline=grid)
    _text(d, (x0, y, x0 + total_w, y + ROW_H),
          f"Present {t['present']}    Absent {t['absent']}    "
          f"Miss Punch {t['miss_punch']}    Late {t['late']}",
          f_head, black, align="left")
    y += ROW_H + 6

    # 6. legend
    lx = x0
    _text(d, (lx, y, lx + 60, y + LEGEND_H), "Legend:", f_small, black, align="left")
    lx += 58
    for key, st in config.STATUS.items():
        if key == "LATE":
            continue
        d.rectangle([lx, y + 5, lx + 15, y + 20], fill=_rgb(st["hex"]), outline=grid)
        label = f"{st['code']} {st['label']}"
        _text(d, (lx + 19, y, lx + 19 + d.textlength(label, font=f_small) + 4, y + LEGEND_H),
              label, f_small, black, align="left")
        lx += 24 + d.textlength(label, font=f_small) + 14

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ============================================================
# Generic flat-table image (miss punch, user detail/summary, inactive)
# ============================================================
CELL_PAD = 12          # horizontal breathing room added to measured text
COL_W_MIN = 46
COL_W_MAX = 360


def _measure(draw, text, font):
    return draw.textlength("" if text is None else str(text), font=font)


def table_image(title, headers, rows, legend=None, left_cols=(2,)) -> io.BytesIO:
    """Render a generic styled table to a PNG.

    ``rows`` mirrors :func:`excel_export.table_xlsx` — a list of
    ``(values_list, hex_or_None)`` tuples so the image never drifts from the
    spreadsheet/screen. ``left_cols`` are 1-based column indices rendered
    left-aligned (defaults to column 2, the Name column).
    """
    f_title = _font(15, bold=True)
    f_head = _font(12, bold=True)
    f_cell = _font(12)
    f_small = _font(11)

    # A throwaway canvas just to measure text before we know the final size.
    scratch = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    ncol = len(headers)
    widths = []
    for i in range(ncol):
        w = _measure(scratch, headers[i], f_head)
        for values, _hex in rows:
            if i < len(values):
                w = max(w, _measure(scratch, values[i], f_cell))
        widths.append(int(max(COL_W_MIN, min(COL_W_MAX, w + CELL_PAD * 2))))

    total_w = sum(widths)
    n = len(rows)
    height = (PAD * 2 + TITLE_H + HEAD_H + max(n, 1) * ROW_H
              + (LEGEND_H if legend else 0) + 6)
    width = total_w + PAD * 2

    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)

    grid = _rgb("808080")
    black = _rgb(config.BLACK)
    head_bg = _rgb(config.COLOR_HEADER)
    sub_bg = _rgb(config.COLOR_SUBHEAD)

    x0, y = PAD, PAD

    # 1. title bar (green)
    d.rectangle([x0, y, x0 + total_w, y + TITLE_H], fill=head_bg, outline=grid)
    _text(d, (x0, y, x0 + total_w, y + TITLE_H), title, f_title, black)
    y += TITLE_H

    # 2. column header (light grey)
    cx = x0
    for header, w in zip(headers, widths):
        d.rectangle([cx, y, cx + w, y + HEAD_H], fill=sub_bg, outline=grid)
        _text(d, (cx, y, cx + w, y + HEAD_H), header, f_head, black)
        cx += w
    y += HEAD_H

    # 3. data rows
    if not rows:
        d.rectangle([x0, y, x0 + total_w, y + ROW_H], fill=(255, 255, 255), outline=grid)
        _text(d, (x0, y, x0 + total_w, y + ROW_H), "No data.", f_cell, black)
        y += ROW_H
    for values, hex_ in rows:
        bg = _rgb(hex_) if hex_ else (255, 255, 255)
        cx = x0
        for col, (w, val) in enumerate(zip(widths, values), 1):
            d.rectangle([cx, y, cx + w, y + ROW_H], fill=bg, outline=grid)
            _text(d, (cx, y, cx + w, y + ROW_H), val, f_cell, black,
                  align="left" if col in left_cols else "center")
            cx += w
        y += ROW_H

    # 4. legend
    if legend:
        lx = x0
        _text(d, (lx, y, lx + 60, y + LEGEND_H), "Legend:", f_small, black, align="left")
        lx += 58
        for item in legend:
            d.rectangle([lx, y + 5, lx + 15, y + 20], fill=_rgb(item["hex"]), outline=grid)
            label = f"{item['code']} {item['label']}"
            _text(d, (lx + 19, y, lx + 19 + d.textlength(label, font=f_small) + 4, y + LEGEND_H),
                  label, f_small, black, align="left")
            lx += 24 + d.textlength(label, font=f_small) + 14

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def monthly_image(data) -> io.BytesIO:
    """Render the monthly muster grid to a PNG (per-cell status colours)."""
    f_title = _font(15, bold=True)
    f_head = _font(11, bold=True)
    f_cell = _font(11)
    f_day = _font(10, bold=True)
    f_small = _font(11)

    scratch = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    days = data["days"]
    name_w = int(max(140, min(300,
        max([_measure(scratch, u["name"], f_cell) for u in data["rows"]] + [80]) + CELL_PAD * 2)))
    day_w = 24
    tail = [("P", 34), ("Abs", 40), ("Miss", 44), ("Late", 40), ("Total", 56)]

    fixed = [("Name", name_w)]
    cols = fixed + [(str(dd), day_w) for dd in days] + tail
    total_w = sum(w for _, w in cols)
    n = len(data["rows"])
    height = PAD * 2 + TITLE_H + HEAD_H + max(n, 1) * ROW_H + LEGEND_H + 6
    width = total_w + PAD * 2

    img = Image.new("RGB", (width, height), "white")
    d = ImageDraw.Draw(img)
    grid = _rgb("808080")
    black = _rgb(config.BLACK)
    head_bg = _rgb(config.COLOR_HEADER)
    sub_bg = _rgb(config.COLOR_SUBHEAD)

    x0, y = PAD, PAD
    d.rectangle([x0, y, x0 + total_w, y + TITLE_H], fill=head_bg, outline=grid)
    _text(d, (x0, y, x0 + total_w, y + TITLE_H), data["month_name"], f_title, black)
    y += TITLE_H

    cx = x0
    for header, w in cols:
        d.rectangle([cx, y, cx + w, y + HEAD_H], fill=sub_bg, outline=grid)
        _text(d, (cx, y, cx + w, y + HEAD_H), header, f_head if header == "Name" else f_day, black,
              align="left" if header == "Name" else "center")
        cx += w
    y += HEAD_H

    for u in data["rows"]:
        cx = x0
        # Name (white)
        d.rectangle([cx, y, cx + name_w, y + ROW_H], fill=(255, 255, 255), outline=grid)
        _text(d, (cx, y, cx + name_w, y + ROW_H), u["name"][:NAME_MAX], f_cell, black, align="left")
        cx += name_w
        for cell in u["cells"]:
            bg = _rgb(cell["hex"]) if cell["code"] else (255, 255, 255)
            d.rectangle([cx, y, cx + day_w, y + ROW_H], fill=bg, outline=grid)
            _text(d, (cx, y, cx + day_w, y + ROW_H), cell["code"], f_cell, black)
            cx += day_w
        for (_h, w), v in zip(tail, (u["present"], u["absent"], u["miss_punch"], u["late"], u["total_hm"])):
            d.rectangle([cx, y, cx + w, y + ROW_H], fill=(255, 255, 255), outline=grid)
            _text(d, (cx, y, cx + w, y + ROW_H), v, f_cell, black)
            cx += w
        y += ROW_H

    lx = x0
    _text(d, (lx, y, lx + 60, y + LEGEND_H), "Legend:", f_small, black, align="left")
    lx += 58
    for item in data["legend"]:
        d.rectangle([lx, y + 5, lx + 15, y + 20], fill=_rgb(item["hex"]), outline=grid)
        label = f"{item['code']} {item['label']}"
        _text(d, (lx + 19, y, lx + 19 + d.textlength(label, font=f_small) + 4, y + LEGEND_H),
              label, f_small, black, align="left")
        lx += 24 + d.textlength(label, font=f_small) + 14

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _safe(name) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in str(name)).strip()


def all_departments_zip(data) -> io.BytesIO:
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dept in data["departments"]:
            png = department_image(dept, data)
            zf.writestr(f"{_safe(dept['name'])}_{data['date_fmt']}.png", png.read())
    zbuf.seek(0)
    return zbuf
