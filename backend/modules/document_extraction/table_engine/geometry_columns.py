"""Column detection by geometry: which printed column is a cell UNDER?

The original detector (column_detector.py) has no coordinates to work with —
it maps a row's Nth token to the table's Nth column. Its own docstring calls
this out as a Known Limitation, and on a photographed invoice it fails in two
ways that cannot be patched from the token list alone:

  * OCR fuses columns. "BPB26038301/28 145.26 ELVAS AM 40/5 TAB" arrives as
    ONE box (Batch + MRP + Product Name). That's one token where the layout
    expects three, so every later token in the row shifts two columns left.
  * Rows leave cells blank. A row with no Free-Qty printed has one token
    fewer, and everything to its right shifts one column left. This is why
    PTR and MRP were landing in each other's fields and product names were
    coming out in the Batch column.

Geometry has neither failure mode. The printed header row gives the x anchor
of each real column (parser hands it over as InvoiceDocument.
table_header_cells); every word of every row is then assigned to the column
band its centre falls in, and the words that land in one band are joined back
into that column's cell. A fused box costs nothing — its words spread across
the bands they're actually printed under. A blank cell costs nothing — that
band simply receives no words, and no other column moves.

Requires a header row to have been found. When one wasn't, the engine falls
back to the index-based detector, which is still the best available guess
with no anchors to align to.
"""

import logging
from statistics import median
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from modules.document_extraction.ocr.models import BoundingBox, Confidence
from modules.document_extraction.parser.models import InvoiceProduct, RowCell
from modules.document_extraction.table_engine.column_detector import IGNORED
from modules.document_extraction.table_engine.models import ColumnType, DetectedColumn
from modules.document_extraction.table_engine.patterns import (
    HEADER_SYNONYMS,
    IGNORED_HEADER_KEYWORDS,
    classify_token,
)

logger = logging.getLogger("document_extraction.geometry_columns")

# A header that resolved fewer real columns than this isn't a layout — it's a
# couple of stray keyword hits, and the index-based detector is the safer bet.
_MIN_RESOLVED_COLUMNS = 4

_HEADER_MATCH_CONFIDENCE = 0.85
_UNKNOWN_CONFIDENCE = 0.2


class ColumnBand(BaseModel):
    """One printed column: what it is, and the x range it owns."""
    column: DetectedColumn
    x_min: float
    x_max: float


# The longest header label worth trying to match, in words ("expiry date",
# "product name", "hsn code" are 2; nothing generic runs past 3).
_MAX_HEADER_PHRASE_WORDS = 3


def build_bands(header_words: List[RowCell]) -> List[ColumnBand]:
    """Turns the header's WORDS into typed, x-bounded columns.

    The words are grouped into header cells by the vocabulary, longest phrase
    first: "PRODUCT NAME" is one column, "Pack QTY FR" is three. That is the
    only grouping signal that survives OCR fusing several header labels into a
    single box — the printed gaps between them are gone by the time the text
    reaches us, and the words' own boxes are then contiguous.

    Returns [] when the header doesn't resolve to a usable layout; the caller
    must treat that as "no geometry available" and fall back."""
    if not header_words:
        return []

    words = sorted(header_words, key=lambda c: c.bbox.x1)
    typed: List[Tuple[RowCell, ColumnType]] = []
    claimed: set = set()

    idx = 0
    while idx < len(words):
        cell, column_type, consumed = _match_phrase_at(words, idx, claimed)
        if column_type in _REAL_TYPES:
            claimed.add(column_type)
        typed.append((cell, column_type))
        idx += consumed

    typed = _merge_adjacent_unknowns(typed)

    resolved = sum(1 for _, t in typed if t in _REAL_TYPES)
    if resolved < _MIN_RESOLVED_COLUMNS:
        logger.info(
            "document_extraction.geometry_columns: header resolved only %d column(s); "
            "falling back to index-based detection", resolved,
        )
        return []

    bands: List[ColumnBand] = []
    for idx, (cell, column_type) in enumerate(typed):
        # A column owns everything from the midpoint between it and its left
        # neighbour to the midpoint between it and its right neighbour — the
        # printed cell text under a header is rarely aligned with the header
        # label itself (numbers right-align, names left-align), so the header
        # cell's own bbox is far too narrow to use as the band.
        x_min = (
            _center(cell) - 1e9 if idx == 0
            else (_center(typed[idx - 1][0]) + _center(cell)) / 2
        )
        x_max = (
            _center(cell) + 1e9 if idx == len(typed) - 1
            else (_center(cell) + _center(typed[idx + 1][0])) / 2
        )
        bands.append(ColumnBand(
            column=DetectedColumn(
                column_index=idx,
                column_type=column_type,
                header_text=cell.text,
                confidence=Confidence(
                    score=_HEADER_MATCH_CONFIDENCE if column_type in _REAL_TYPES else _UNKNOWN_CONFIDENCE,
                ),
                evidence=[f"header:{cell.text}", f"x:{cell.bbox.x1}-{cell.bbox.x2}"],
            ),
            x_min=x_min,
            x_max=x_max,
        ))
    return bands


_REAL_TYPES = {t for t in ColumnType if t != ColumnType.UNKNOWN}


def _merge_adjacent_unknowns(
    typed: List[Tuple[RowCell, ColumnType]],
) -> List[Tuple[RowCell, ColumnType]]:
    """Consecutive unrecognized header words are ONE unnamed column, not one
    each. A header label the vocabulary doesn't know still arrives as several
    words — the Nathan Medicals bill's "Description" column came back as "MAIN
    PRODUCTS" — and treating each word as its own column cuts that column in
    half, so the medicine names printed under it get split down the middle
    ("AMLODAC" in one column, "5MG" in the next). There is nothing to tell the
    two halves apart, so there is no reason to keep them apart."""
    merged: List[Tuple[RowCell, ColumnType]] = []
    for cell, column_type in typed:
        if (
            column_type == ColumnType.UNKNOWN
            and merged and merged[-1][1] == ColumnType.UNKNOWN
        ):
            merged[-1] = (_merge_cells([merged[-1][0], cell]), ColumnType.UNKNOWN)
        else:
            merged.append((cell, column_type))
    return merged


def _match_phrase_at(
    words: List[RowCell], start: int, claimed: set,
) -> Tuple[RowCell, ColumnType, int]:
    """The longest header label starting at `words[start]`, as a single cell.
    Returns (cell, type, words_consumed) — an unrecognized word still becomes
    a one-word UNKNOWN cell rather than being dropped, because it owns real
    estate on the page: without a band there, the values printed under it
    would drift into the neighbouring real column."""
    for length in range(min(_MAX_HEADER_PHRASE_WORDS, len(words) - start), 0, -1):
        group = words[start:start + length]
        match = _match_header_words(group)
        if match is None:
            continue
        # IGNORED (a Loc/Taxable column we deliberately have no field for), or
        # a label already claimed by a column further left — this invoice
        # prints Disc% twice — is still a real column, just an unnamed one.
        column_type = (
            match if match is not IGNORED and match not in claimed
            else ColumnType.UNKNOWN
        )
        return _merge_cells(group), column_type, length

    return words[start], ColumnType.UNKNOWN, 1


def _normalize_label(text: str) -> str:
    return " ".join(text.strip().lower().split())


# Exact-phrase lookups, NOT column_detector.match_header_text's substring
# test. Substring matching is right when you already know the cell's extent
# and only need to name it; here the extent is what's being decided, and a
# substring test makes every window match something — "product name pack"
# contains "product name", so a greedy 3-word window would swallow the Pack
# column into Product Name and every column to its right would inherit the
# wrong band.
_SYNONYM_LOOKUP = {
    _normalize_label(synonym): ctype
    for ctype, synonyms in HEADER_SYNONYMS.items()
    for synonym in synonyms
}
_IGNORED_LOOKUP = {_normalize_label(keyword) for keyword in IGNORED_HEADER_KEYWORDS}


def _match_header_words(group: List[RowCell]):
    """Header vocabulary lookup for one candidate phrase, tolerant of the
    punctuation OCR sprinkles through printed labels — "M.R.P" and "M.RP" both
    have to reach "mrp", and "Exp.Date" has to reach "exp date"."""
    text = " ".join(cell.text for cell in group)
    for variant in (text, text.replace(".", ""), text.replace(".", " ")):
        label = _normalize_label(variant)
        if not label:
            continue
        if label in _IGNORED_LOOKUP:
            return IGNORED
        if label in _SYNONYM_LOOKUP:
            return _SYNONYM_LOOKUP[label]
    return None


def _merge_cells(cells: List[RowCell]) -> RowCell:
    return RowCell(
        text=" ".join(c.text for c in cells),
        bbox=BoundingBox(
            x1=min(c.bbox.x1 for c in cells), y1=min(c.bbox.y1 for c in cells),
            x2=max(c.bbox.x2 for c in cells), y2=max(c.bbox.y2 for c in cells),
        ),
    )


def fit_bands(bands: List[ColumnBand], rows: List[InvoiceProduct]) -> List[ColumnBand]:
    """Slides the header's bands sideways to sit over the data they describe.

    A phone photo of an invoice has perspective: the table's columns do not sit
    at exactly the x the header row printed them at, and the further down the
    page, the further they drift. Half a column of drift is enough to put every
    Qty under the Free-Qty header. The header still says what the columns ARE
    and in what order — that never drifts — so the fix is to keep the layout
    and shift it, choosing the shift whose resulting cells best match what each
    column is supposed to hold (a Qty column full of integers, an MRP column
    full of money) per patterns.classify_token.

    Only shifts. Nothing here re-orders or re-types a column: a fit that beats
    the header's own reading of the table would be a fit that's overfitting."""
    if not bands or not rows:
        return bands

    width = median([band.x_max - band.x_min for band in bands if _is_bounded(band)] or [0.0])
    if width <= 0:
        return bands

    candidates = [width * step / 10.0 for step in range(-10, 11)]
    best_shift, best_score = 0.0, _fit_score(bands, rows, 0.0)
    for shift in candidates:
        score = _fit_score(bands, rows, shift)
        if score > best_score:
            best_shift, best_score = shift, score

    if best_shift == 0.0:
        return bands
    logger.info(
        "document_extraction.geometry_columns: fitted header bands to data by %+.1fpx "
        "(fit score %.3f)", best_shift, best_score,
    )
    return [_shift(band, best_shift) for band in bands]


def _fit_score(bands: List[ColumnBand], rows: List[InvoiceProduct], shift: float) -> float:
    """How well the cells that land in each column match what that column is
    supposed to hold, summed over the table. Summed, not averaged: a shift that
    drops half the cells outside every band must not win by scoring the handful
    it keeps."""
    shifted = [_shift(band, shift) for band in bands]
    type_by_index = {b.column.column_index: b.column.column_type for b in shifted}

    total = 0.0
    for row in rows:
        for index, text in assign_row(row, shifted).items():
            column_type = type_by_index[index]
            if column_type in _REAL_TYPES and text:
                total += classify_token(text).get(column_type, 0.0)
    return total


def _shift(band: ColumnBand, dx: float) -> ColumnBand:
    return band.model_copy(update={
        "x_min": band.x_min + dx if _is_finite(band.x_min) else band.x_min,
        "x_max": band.x_max + dx if _is_finite(band.x_max) else band.x_max,
    })


_OPEN_EDGE = 1e8


def _is_finite(x: float) -> bool:
    return abs(x) < _OPEN_EDGE


def _is_bounded(band: ColumnBand) -> bool:
    return _is_finite(band.x_min) and _is_finite(band.x_max)


def ensure_name_band(bands: List[ColumnBand], rows: List[InvoiceProduct]) -> List[ColumnBand]:
    """Every product table has a product-name column, whether or not its header
    label survived OCR — on the Nathan Medicals bill "Description" came back as
    "MAIN PRODUCTS", which matches no header vocabulary, and the medicine names
    would have been dropped as an unnamed column. So if no band claimed Product
    Name, the unnamed band whose contents are most alphabetic becomes it.

    Content, not position: which column holds the names varies by supplier, but
    "the column full of words rather than numbers" does not."""
    if any(b.column.column_type == ColumnType.PRODUCT_NAME for b in bands):
        return bands

    alpha_by_band: Dict[int, List[float]] = {}
    for row in rows:
        for index, text in assign_row(row, bands).items():
            if text:
                alpha_by_band.setdefault(index, []).append(
                    sum(c.isalpha() for c in text) / len(text)
                )

    candidates = [
        (sum(ratios) / len(ratios), band)
        for band in bands
        for ratios in [alpha_by_band.get(band.column.column_index, [])]
        if ratios and band.column.column_type == ColumnType.UNKNOWN
    ]
    if not candidates:
        return bands

    alpha_ratio, winner = max(candidates, key=lambda c: c[0])
    logger.info(
        "document_extraction.geometry_columns: no Product Name header; using column %d (%r, "
        "%.0f%% alphabetic) as the name column",
        winner.column.column_index, winner.column.header_text, alpha_ratio * 100,
    )
    return [
        band if band is not winner else band.model_copy(update={
            "column": band.column.model_copy(update={
                "column_type": ColumnType.PRODUCT_NAME,
                "confidence": Confidence(score=0.4),
                "evidence": band.column.evidence + ["fallback:most_alpha_column"],
            }),
        })
        for band in bands
    ]


def name_band_index(bands: List[ColumnBand]) -> Optional[int]:
    return next(
        (b.column.column_index for b in bands if b.column.column_type == ColumnType.PRODUCT_NAME),
        None,
    )


class RegroupedRow(BaseModel):
    """A table row rebuilt after the columns are known: cell text per column,
    plus what the row was reconstructed from."""
    cells: Dict[int, str] = {}
    ocr_row_text: str = ""
    confidence: float = 0.0


def regroup_rows(
    rows: List[InvoiceProduct], bands: List[ColumnBand], name_band: Optional[int],
) -> List[RegroupedRow]:
    """Rebuilds the table's rows once the columns are known — a row is the cells
    that share a vertical band, with each word first put in the column it is
    printed under (and a name fused into a money box put back, see
    _reassign_stray_word).

    KNOWN LIMITATION — staggered layouts. Some legacy bills print the
    Description column on a HIGHER baseline than the batch/price grid beside
    it (this project's Nathan Medicals bill does). Grouping by vertical
    position then pairs a product's name with the NEXT row's numbers, and
    nothing here detects that: the two grids don't agree on a row count to pair
    them by (the price grid itself splits, batch on one baseline and money on
    another), so there is no correspondence to recover. On such an invoice the
    columns are right and the values are right, but the name against a row may
    belong to its neighbour — Review has to confirm the pairing. Fixing it
    needs a row anchor the layout actually guarantees (the printed S.No), which
    is a separate piece of work."""
    placed = [
        (cell, band_idx, row)
        for row in rows
        for cell in row.cells
        for band_idx in [_reassign_stray_word(cell, _band_for(cell, bands), bands, name_band)]
        if band_idx is not None
    ]
    if not placed:
        return []
    return [_to_regrouped(cluster) for cluster in _cluster_by_y(placed)]


# Columns that hold numbers, plus the unnamed ones. A word of pure letters has
# no business in any of them — but it does in Batch, Pack, HSN or Expiry, whose
# cells legitimately read "10'S" or "TAB", so those are left alone.
_WORDLESS_TYPES = {
    ColumnType.QTY, ColumnType.FREE_QTY, ColumnType.PTR, ColumnType.PURCHASE_RATE,
    ColumnType.MRP, ColumnType.GST_PERCENT, ColumnType.DISCOUNT_PERCENT,
    ColumnType.DISCOUNT_AMOUNT, ColumnType.AMOUNT, ColumnType.SERIAL_NO,
    ColumnType.UNKNOWN,
}


def _reassign_stray_word(
    cell: RowCell, band_idx: Optional[int], bands: List[ColumnBand], name_band: Optional[int],
) -> Optional[int]:
    """A word of letters that landed in a money column belongs to the product
    name, and is put back there.

    This is the one place the approximation in the word boxes shows. When OCR
    fuses "387.00 ANTEJ PASTE 100GM" (MRP + name) into a single box, its words
    are spread across that box's width by character count, so the first word or
    two of the name can fall a few pixels short and land under MRP — and the
    name imports as "100GM". A price column never holds a word; the name column
    does. Anything with a digit in it (a "5%G" tax code, a "10ML" pack) is left
    exactly where the geometry put it."""
    if band_idx is None or name_band is None or band_idx == name_band:
        return band_idx
    if bands[band_idx].column.column_type not in _WORDLESS_TYPES:
        return band_idx

    text = cell.text.strip()
    is_word = len(text) >= 3 and any(c.isalpha() for c in text) and not any(c.isdigit() for c in text)
    return name_band if is_word else band_idx


def _cluster_by_y(placed: List[Tuple[RowCell, int, InvoiceProduct]]) -> List[List[Tuple]]:
    """Groups cells into rows by vertical centre — same median-anchored banding
    as the parser's own row grouping (generic_invoice_parser._group_into_rows),
    so one tall cell can't chain a row into the one below it."""
    if not placed:
        return []

    tolerance = _ROW_BAND_TOLERANCE * median(
        [max(cell.bbox.y2 - cell.bbox.y1, 1.0) for cell, _, _ in placed]
    )
    ordered = sorted(placed, key=lambda item: (_y_center_of(item[0]), item[0].bbox.x1))

    clusters: List[List[Tuple]] = [[ordered[0]]]
    centers = [_y_center_of(ordered[0][0])]
    for item in ordered[1:]:
        center = _y_center_of(item[0])
        if abs(center - median(centers)) <= tolerance:
            clusters[-1].append(item)
            centers.append(center)
        else:
            clusters.append([item])
            centers = [center]
    return clusters


def _to_regrouped(cluster: List[Tuple[RowCell, int, InvoiceProduct]]) -> RegroupedRow:
    by_band: Dict[int, List[RowCell]] = {}
    for cell, band_idx, _row in cluster:
        by_band.setdefault(band_idx, []).append(cell)

    source_rows = {id(row): row for _c, _b, row in cluster}.values()
    return RegroupedRow(
        cells={
            idx: " ".join(c.text for c in sorted(cells, key=lambda c: c.bbox.x1)).strip()
            for idx, cells in by_band.items()
        },
        ocr_row_text=" ".join(
            cell.text for cell, _b, _r in sorted(cluster, key=lambda item: item[0].bbox.x1)
        ),
        confidence=(
            sum(r.confidence.score for r in source_rows) / len(source_rows)
            if source_rows else 0.0
        ),
    )


# Same reasoning as the parser's own row banding (generic_invoice_parser.
# _group_into_rows): a cell belongs to the row whose centre it sits closest to,
# measured against the row's median so one tall cell can't drag the row down
# into the next one.
_ROW_BAND_TOLERANCE = 0.6


def _y_center_of(cell: RowCell) -> float:
    return (cell.bbox.y1 + cell.bbox.y2) / 2.0


def assign_row(row: InvoiceProduct, bands: List[ColumnBand]) -> Dict[int, str]:
    """{column_index: cell text} for one row — every word of the row placed
    in the band it is printed under, then the words of each band joined back
    left-to-right into that column's value."""
    by_band: Dict[int, List[RowCell]] = {}
    for cell in row.cells:
        band_idx = _band_for(cell, bands)
        if band_idx is not None:
            by_band.setdefault(band_idx, []).append(cell)

    return {
        idx: " ".join(c.text for c in sorted(cells, key=lambda c: c.bbox.x1)).strip()
        for idx, cells in by_band.items()
    }


def _band_for(cell: RowCell, bands: List[ColumnBand]) -> Optional[int]:
    center = _center(cell)
    for band in bands:
        if band.x_min <= center < band.x_max:
            return band.column.column_index
    return None


def _center(cell: RowCell) -> float:
    return (cell.bbox.x1 + cell.bbox.x2) / 2.0


def row_has_geometry(rows: List[InvoiceProduct]) -> bool:
    """Whether the rows actually carry cell boxes — an OCR provider or a
    stored ocr_json from before RowCell existed carries none, and the caller
    must fall back rather than silently produce an empty table."""
    return any(row.cells for row in rows)


def median_row_span(rows: List[InvoiceProduct]) -> float:
    spans = [
        max(c.bbox.x2 for c in row.cells) - min(c.bbox.x1 for c in row.cells)
        for row in rows if row.cells
    ]
    return median(spans) if spans else 0.0
