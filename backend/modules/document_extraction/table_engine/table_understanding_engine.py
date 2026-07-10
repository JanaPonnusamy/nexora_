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

from typing import Dict, List, Optional, Tuple

from modules.document_extraction.ocr.models import Confidence
from modules.document_extraction.parser.models import InvoiceDocument, InvoiceProduct
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
        return None


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
