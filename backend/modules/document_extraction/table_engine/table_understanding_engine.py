"""Chunk 7 — Product Table Understanding Engine.

Converts InvoiceDocument.products into StructuredProductRow. This is the
sole entry point downstream code (Chunk 9's product extraction, a future
Review UI debug panel) should use — nobody outside this package should call
column_detector.py / row_reconstructor.py / patterns.py directly.

Pure transform, no I/O:

  1. split_merged_rows   — undo OCR row-grouping that fused two physical
                            rows into one wide row (row_reconstructor.py).
  2. detect_columns       — the generic column detector, using pattern +
                            position + header-hint + neighbour signals
                            (column_detector.py). Never supplier-specific.
  3. merge_wrapped_rows   — fold wrapped/continuation name-only rows into
                            the data row they belong to, now that the
                            layout tells us which tokens are "real" data
                            (row_reconstructor.py).
  4. align + build        — monotonic token-to-column alignment
                            (tolerant of missing/blank cells) and
                            self-validation (row confidence, column
                            confidence, missing/ambiguous columns).

Never: writes a database, resolves a ProductCode, calls a repository,
searches SupplierProductMapping (models.py docstring).
"""

import re
from typing import Dict, List, Optional, Tuple

from modules.document_extraction.ocr.models import Confidence
from modules.document_extraction.parser.models import InvoiceDocument, InvoiceProduct
from modules.document_extraction.table_engine import geometry_columns
from modules.document_extraction.table_engine.geometry_columns import ColumnBand
from modules.document_extraction.table_engine.column_detector import (
    detect_columns,
    detect_expected_column_count,
    find_header_hint,
)
from modules.document_extraction.table_engine.models import (
    ColumnType,
    DetectedColumn,
    OUTPUT_COLUMN_TYPES,
    RowIssue,
    StructuredProductRow,
    TableLayout,
    TableUnderstandingResult,
)
from modules.document_extraction.table_engine.patterns import classify_token
from modules.document_extraction.table_engine.row_reconstructor import (
    merge_wrapped_rows,
    split_merged_rows,
)

_SKIP_TOKEN_PENALTY = 0.12
_SKIP_COLUMN_PENALTY = 0.08
# A token may still align to a column it doesn't pattern-match at all (e.g.
# OCR garbled a name cell into something that fails every regex) rather
# than being dropped outright — at a heavy discount, so a confident
# alternative alignment always wins when one exists.
_MIN_MATCH_FLOOR = 0.05
_UNKNOWN_COLUMN_NEUTRAL_SCORE = 0.2
_AMBIGUOUS_COLUMN_THRESHOLD = 0.5


class TableUnderstandingEngine:
    def understand(self, document: InvoiceDocument) -> TableUnderstandingResult:
        rows = document.products
        if not rows:
            return TableUnderstandingResult(
                layout=TableLayout(
                    expected_column_count=0, columns=[], header_source=None, row_count=0,
                ),
                rows=[],
            )

        # Geometry first, always, when the page gives us the anchors for it:
        # a cell placed under the column it is physically printed under can't
        # be shifted by a fused OCR box or a blank cell, and both of those are
        # routine on a photographed invoice (geometry_columns.py). The
        # index-based path below is the fallback for a table whose header row
        # was never found — it is a guess, and it degrades exactly as you'd
        # expect when a row is ragged.
        if geometry_columns.row_has_geometry(rows):
            bands = geometry_columns.build_bands(document.table_header_cells)
            if bands:
                return self._understand_by_geometry(rows, geometry_columns.fit_bands(bands, rows))

        provisional_count = detect_expected_column_count(rows)
        rows = split_merged_rows(rows, provisional_count)
        expected_column_count = detect_expected_column_count(rows)

        header_hint = find_header_hint(document.unassigned_lines)
        columns = detect_columns(rows, expected_column_count, header_hint)

        rows, merged_extra_text = merge_wrapped_rows(rows, expected_column_count)

        structured_rows = [
            self._build_row(row, columns, extra_name_text=merged_extra_text.get(row.line_number))
            for row in rows
        ]

        layout = TableLayout(
            expected_column_count=expected_column_count,
            columns=columns,
            header_source="header_row" if header_hint else (
                "position_and_pattern" if columns else None
            ),
            row_count=len(structured_rows),
        )
        return TableUnderstandingResult(layout=layout, rows=structured_rows)

    def _understand_by_geometry(
        self, rows: List[InvoiceProduct], bands: List[ColumnBand],
    ) -> TableUnderstandingResult:
        bands = geometry_columns.ensure_name_band(bands, rows)
        columns = [band.column for band in bands]
        regrouped = geometry_columns.regroup_rows(
            rows, bands, geometry_columns.name_band_index(bands),
        )
        structured = [
            self._build_row_by_geometry(row, bands, line_number)
            for line_number, row in enumerate(regrouped, start=1)
        ]
        structured = _fold_wrapped_name_rows(structured)

        layout = TableLayout(
            expected_column_count=len(columns),
            columns=columns,
            header_source="header_geometry",
            row_count=len(structured),
        )
        return TableUnderstandingResult(layout=layout, rows=structured)

    def _build_row_by_geometry(
        self, row: geometry_columns.RegroupedRow, bands: List[ColumnBand], line_number: int,
    ) -> StructuredProductRow:
        structured = StructuredProductRow(
            line_number=line_number,
            ocr_row_text=row.ocr_row_text,
        )

        column_confidence: Dict[str, float] = {}
        for band in bands:
            text = row.cells.get(band.column.column_index, "").strip()
            if not text or band.column.column_type not in OUTPUT_COLUMN_TYPES:
                continue
            _apply_field(structured, band.column.column_type, text)
            # The cell is where it is; how much to trust it is a question about
            # the column's own identification and how well the text matches the
            # shape that column should hold (a name in a Qty column is still
            # reported, at a confidence that says "look at me").
            pattern_score = classify_token(text).get(band.column.column_type, 0.0)
            column_confidence[band.column.column_type.value] = round(
                min(1.0, 0.5 * band.column.confidence.score + 0.5 * pattern_score) + 0.25, 4,
            )

        output_types = {b.column.column_type for b in bands if b.column.column_type in OUTPUT_COLUMN_TYPES}
        missing = sorted(t.value for t in output_types if t.value not in column_confidence)
        structured.missing_columns = missing
        structured.column_confidence = column_confidence

        ocr_score = row.confidence
        match_scores = list(column_confidence.values())
        mean_match = sum(match_scores) / len(match_scores) if match_scores else 0.0
        completeness = 1.0 - (len(missing) / len(output_types)) if output_types else 0.5
        structured.confidence = Confidence(score=round(
            max(0.0, min(1.0, 0.35 * ocr_score + 0.4 * mean_match + 0.25 * completeness)), 4,
        ))

        if missing:
            structured.issues.append(RowIssue(
                code="MISSING_COLUMN", detail=f"No cell aligned for: {', '.join(missing)}",
            ))
        return structured

    def _build_row(
        self, row: InvoiceProduct, columns: List[DetectedColumn], extra_name_text: Optional[str],
    ) -> StructuredProductRow:
        assignment = _align_tokens_to_columns(row.tokens, columns)

        values: Dict[ColumnType, Tuple[str, float]] = {}
        for token_idx, column_idx, score in assignment:
            column = columns[column_idx]
            if column.column_type not in OUTPUT_COLUMN_TYPES:
                continue
            values[column.column_type] = (row.tokens[token_idx], score)

        structured = StructuredProductRow(
            line_number=row.line_number,
            ocr_row_text=row.ocr_row_text,
            bbox=row.region.bbox if row.region else None,
        )

        column_confidence: Dict[str, float] = {}
        for ctype, (raw_value, score) in values.items():
            _apply_field(structured, ctype, raw_value)
            column_confidence[ctype.value] = round(score, 4)

        if structured.product_name is None and row.product_name_guess:
            structured.product_name = row.product_name_guess
            column_confidence.setdefault(ColumnType.PRODUCT_NAME.value, 0.3)
            structured.issues.append(RowIssue(
                code="PRODUCT_NAME_FALLBACK",
                detail=(
                    "No column aligned confidently to Product Name; used the "
                    "parser's longest-token heuristic guess instead."
                ),
            ))

        if extra_name_text:
            # A wrapped/continuation row was folded into this one
            # (row_reconstructor.merge_wrapped_rows) — append its text onto
            # whichever product name we ended up with, whether that came
            # from a real column match or the fallback guess above.
            structured.product_name = f"{structured.product_name or ''} {extra_name_text}".strip()

        detected_output_types = {c.column_type for c in columns if c.column_type in OUTPUT_COLUMN_TYPES}
        missing = sorted(t.value for t in (detected_output_types - set(values.keys())))
        structured.missing_columns = missing

        ambiguous = sorted({
            c.header_text or f"column_{c.column_index}"
            for c in columns
            if c.column_type in OUTPUT_COLUMN_TYPES and c.confidence.score < _AMBIGUOUS_COLUMN_THRESHOLD
        })
        structured.ambiguous_columns = ambiguous
        structured.column_confidence = column_confidence

        ocr_score = row.confidence.score if row.confidence else 0.5
        match_scores = list(column_confidence.values())
        mean_match = sum(match_scores) / len(match_scores) if match_scores else 0.0
        completeness = (
            1.0 - (len(missing) / len(detected_output_types))
            if detected_output_types else 0.5
        )
        row_score = 0.35 * ocr_score + 0.4 * mean_match + 0.25 * completeness
        structured.confidence = Confidence(score=round(max(0.0, min(1.0, row_score)), 4))

        if extra_name_text:
            structured.issues.append(RowIssue(
                code="WRAPPED_NAME_MERGED",
                detail="A following text-only continuation row was folded into this row's product name.",
            ))
        if missing:
            structured.issues.append(RowIssue(
                code="MISSING_COLUMN", detail=f"No cell aligned for: {', '.join(missing)}",
            ))
        if ambiguous:
            structured.issues.append(RowIssue(
                code="AMBIGUOUS_COLUMN", detail=f"Low-confidence column detection: {', '.join(ambiguous)}",
            ))

        return structured


_DATA_FIELDS = ("batch", "expiry", "qty", "free_qty", "ptr", "purchase_rate", "mrp", "amount")


def _fold_wrapped_name_rows(rows: List[StructuredProductRow]) -> List[StructuredProductRow]:
    """Folds a name-only row into the row above it — the geometry counterpart
    of row_reconstructor.merge_wrapped_rows. A long product name wraps onto a
    second printed line with nothing else on it; that line groups into its own
    visual row and would otherwise import as a product with no batch, no qty
    and no price."""
    folded: List[StructuredProductRow] = []
    for row in rows:
        is_name_only = row.product_name and all(
            getattr(row, field) is None for field in _DATA_FIELDS
        )
        if is_name_only and folded:
            previous = folded[-1]
            previous.product_name = f"{previous.product_name or ''} {row.product_name}".strip()
            previous.issues.append(RowIssue(
                code="WRAPPED_NAME_MERGED",
                detail="A following text-only continuation row was folded into this row's product name.",
            ))
            continue
        folded.append(row)

    for line_number, row in enumerate(folded, start=1):
        row.line_number = line_number
    return folded


def _apply_field(structured: StructuredProductRow, ctype: ColumnType, raw_value: str) -> None:
    text = raw_value.strip()
    if ctype == ColumnType.PRODUCT_NAME:
        structured.product_name = text
    elif ctype == ColumnType.PACK:
        structured.pack = text
    elif ctype == ColumnType.HSN:
        structured.hsn = text
    elif ctype == ColumnType.BATCH:
        structured.batch = text
    elif ctype == ColumnType.EXPIRY:
        structured.expiry = text
    elif ctype == ColumnType.QTY:
        structured.qty = _to_float(text)
    elif ctype == ColumnType.FREE_QTY:
        structured.free_qty = _to_float(text)
    elif ctype == ColumnType.PTR:
        structured.ptr = _to_float(text)
    elif ctype == ColumnType.PURCHASE_RATE:
        structured.purchase_rate = _to_float(text)
    elif ctype == ColumnType.MRP:
        structured.mrp = _to_float(text)
    elif ctype == ColumnType.GST_PERCENT:
        structured.gst_percent = _to_float(text)
    elif ctype == ColumnType.DISCOUNT_PERCENT:
        structured.discount_percent = _to_float(text)
    elif ctype == ColumnType.AMOUNT:
        structured.amount = _to_float(text)


def _to_float(text: str) -> Optional[float]:
    cleaned = text.replace(",", "").rstrip("%").strip()
    try:
        return float(cleaned)
    except ValueError:
        # Printed GST cells often include a trailing tax marker (for example
        # `5 % G`). Keep the number only when everything else is that marker;
        # a misaligned product name such as `AMLODAC 5MG` must stay nonnumeric.
        match = re.fullmatch(
            r"\s*([-+]?\d+(?:\.\d+)?)\s*%?\s*(?:G(?:ST)?)?\s*",
            cleaned,
            flags=re.IGNORECASE,
        )
        return float(match.group(1)) if match else None


def _align_tokens_to_columns(
    tokens: List[str], columns: List[DetectedColumn],
) -> List[Tuple[int, int, float]]:
    """Needleman-Wunsch-style monotonic alignment: tokens and columns both
    stay in left-to-right order, but either side may have unmatched
    elements — a missing cell skips a column, OCR noise/an extra token
    skips a token — rather than forcing a fixed positional match. This is
    what lets a genuinely short/ragged row (Missing Cell, Blank Cell) still
    line up correctly against the table's full column layout, without any
    supplier-specific handling.

    Returns a list of (token_index, column_index, match_score) triples in
    left-to-right order.
    """
    n, m = len(tokens), len(columns)
    if n == 0 or m == 0:
        return []

    token_scores = [classify_token(tokens[i]) for i in range(n)]

    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    back = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] - _SKIP_TOKEN_PENALTY
        back[i][0] = "up"
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] - _SKIP_COLUMN_PENALTY
        back[0][j] = "left"

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            column_type = columns[j - 1].column_type
            match_score = (
                _UNKNOWN_COLUMN_NEUTRAL_SCORE if column_type == ColumnType.UNKNOWN
                else token_scores[i - 1].get(column_type, 0.0)
            )
            match_value = dp[i - 1][j - 1] + max(match_score, _MIN_MATCH_FLOOR)
            skip_token_value = dp[i - 1][j] - _SKIP_TOKEN_PENALTY
            skip_column_value = dp[i][j - 1] - _SKIP_COLUMN_PENALTY

            best = max(match_value, skip_token_value, skip_column_value)
            dp[i][j] = best
            if best == match_value:
                back[i][j] = "diag"
            elif best == skip_token_value:
                back[i][j] = "up"
            else:
                back[i][j] = "left"

    assignment: List[Tuple[int, int, float]] = []
    i, j = n, m
    while i > 0 and j > 0:
        direction = back[i][j]
        if direction == "diag":
            column_type = columns[j - 1].column_type
            score = (
                _UNKNOWN_COLUMN_NEUTRAL_SCORE if column_type == ColumnType.UNKNOWN
                else token_scores[i - 1].get(column_type, 0.0)
            )
            assignment.append((i - 1, j - 1, max(score, _MIN_MATCH_FLOOR)))
            i, j = i - 1, j - 1
        elif direction == "up":
            i -= 1
        else:
            j -= 1
    assignment.reverse()
    return assignment
