"""Chunk 7 — Product Table Understanding Engine. Row reconstruction.

Normalizes the InvoiceDocument.products list before column alignment so a
handful of common OCR artefacts don't get misread as real table structure:

  * Merged OCR Boxes  — two physical rows the parser's row-grouper fused
                         into one wide row because they y-overlapped just
                         enough (split_merged_rows). Detected as a token
                         count that's an exact multiple of the table's
                         modal column count.
  * Wrapped Product Names / Multi-line Product Description / Split OCR
    Rows — a short, all-text continuation row immediately following a real
                         data row gets folded into that row's product name
                         instead of becoming its own, mostly-empty
                         StructuredProductRow (merge_wrapped_rows). This one
                         mechanism covers both "a long name wrapped onto a
                         second line" and "a data row's cells split across
                         two OCR rows and the name fragment landed on its
                         own" — both look identical once the tokens are on
                         the page: a short row with no strong data pattern
                         attached to the row right before it.

Missing/blank cells are NOT filled in here — that's the alignment step's
job (table_understanding_engine.py), since it needs the detected column
layout to know what "missing" even means for a given row.
"""

from typing import Dict, List, Tuple

from modules.document_extraction.ocr.models import BoundingBox
from modules.document_extraction.parser.models import InvoiceProduct
from modules.document_extraction.table_engine.models import ColumnType
from modules.document_extraction.table_engine.patterns import classify_token

_STRONG_NUMERIC_TYPES = {
    ColumnType.EXPIRY, ColumnType.QTY, ColumnType.FREE_QTY, ColumnType.PTR,
    ColumnType.PURCHASE_RATE, ColumnType.MRP, ColumnType.GST_PERCENT,
    ColumnType.DISCOUNT_PERCENT, ColumnType.AMOUNT, ColumnType.HSN,
}
_STRONG_MATCH_THRESHOLD = 0.4


def split_merged_rows(
    rows: List[InvoiceProduct], expected_column_count: int,
) -> List[InvoiceProduct]:
    if expected_column_count <= 0:
        return rows

    result: List[InvoiceProduct] = []
    for row in rows:
        token_count = len(row.tokens)
        multiple = token_count // expected_column_count if expected_column_count else 0
        is_clean_multiple = (
            token_count > expected_column_count
            and token_count % expected_column_count == 0
            and multiple > 1
        )
        if not is_clean_multiple:
            result.append(row)
            continue
        for i in range(multiple):
            chunk = row.tokens[i * expected_column_count:(i + 1) * expected_column_count]
            result.append(row.model_copy(update={
                "tokens": chunk,
                "ocr_row_text": "  ".join(chunk),
            }))
    return result


def _is_text_only(tokens: List[str]) -> bool:
    for token in tokens:
        scores = classify_token(token)
        if any(scores.get(t, 0.0) >= _STRONG_MATCH_THRESHOLD for t in _STRONG_NUMERIC_TYPES):
            return False
    return True


def merge_wrapped_rows(
    rows: List[InvoiceProduct], expected_column_count: int,
) -> Tuple[List[InvoiceProduct], Dict[int, str]]:
    """Returns (retained_rows, merged_extra_text) — merged_extra_text maps
    the retained row's line_number to the continuation text folded into it
    (joined, if more than one wrap happened). The caller (
    table_understanding_engine.py) is responsible for appending this onto
    the row's final `product_name` field once column alignment has run —
    this function only normalizes `ocr_row_text`/`product_name_guess` on
    the InvoiceProduct, it never touches `tokens`, so it must not be relied
    on to populate the structured output by itself."""
    if not rows:
        return rows, {}

    merged_extra: Dict[int, str] = {}
    retained: List[InvoiceProduct] = [rows[0]]
    short_threshold = max(1, expected_column_count // 2) if expected_column_count else 1

    for row in rows[1:]:
        is_short = len(row.tokens) <= short_threshold
        if is_short and retained and _is_text_only(row.tokens):
            prev = retained[-1]
            extra_text = " ".join(t for t in row.tokens if t).strip() or row.ocr_row_text.strip()
            if not extra_text:
                retained.append(row)
                continue
            merged_bbox = _union_bbox(prev, row)
            prev_region = (
                prev.region.model_copy(update={"bbox": merged_bbox})
                if prev.region and merged_bbox else prev.region
            )
            retained[-1] = prev.model_copy(update={
                "ocr_row_text": f"{prev.ocr_row_text}  {extra_text}".strip(),
                "product_name_guess": f"{prev.product_name_guess or ''} {extra_text}".strip(),
                "region": prev_region,
            })
            existing = merged_extra.get(prev.line_number)
            merged_extra[prev.line_number] = f"{existing} {extra_text}".strip() if existing else extra_text
        else:
            retained.append(row)

    return retained, merged_extra


def _union_bbox(prev: InvoiceProduct, row: InvoiceProduct) -> BoundingBox:
    if not prev.region:
        return row.region.bbox if row.region else None
    if not row.region:
        return prev.region.bbox
    a, b = prev.region.bbox, row.region.bbox
    return BoundingBox(
        x1=min(a.x1, b.x1), y1=min(a.y1, b.y1),
        x2=max(a.x2, b.x2), y2=max(a.y2, b.y2),
    )
