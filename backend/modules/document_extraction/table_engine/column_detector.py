"""Chunk 7 — Product Table Understanding Engine. Generic column detector.

No supplier name is ever referenced here — not "Nathan Medicals", not
"Thanthai Pharma". Detection uses only the four generic signals named in
the chunk brief:

  * Column Header    — best-effort header-row text, recovered from
                        InvoiceDocument.unassigned_lines when the generic
                        parser (Chunk 6) left a header-shaped line there
                        (find_header_hint). Never assumed present.
  * Relative Position — a token's index within its row, compared across all
                        rows of the same width. Real per-token bounding
                        boxes aren't part of the current OCR/parser output
                        contract (InvoiceProduct.tokens is a plain
                        List[str]) — see the module's Known Limitations
                        note — so "position" here is index-based, not
                        pixel-based.
  * Data Pattern      — regex/heuristic classification (patterns.py),
                        aggregated per column across every row that has the
                        table's modal token count.
  * Neighbour Columns  — a handful of adjacency priors (Free Qty follows
                        Qty, Amount is usually the rightmost/largest
                        decimal-like column, Serial No is column 0, ...)
                        used only to break ties between similarly-scored
                        candidates — never to invent a column with no
                        pattern evidence.

Column assignment is a single greedy pass: every (column, candidate type)
pair is scored, then claimed highest-score-first, so no two columns fight
over the same canonical field and no column is left unexamined.
"""

import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from modules.document_extraction.ocr.models import Confidence
from modules.document_extraction.parser.models import InvoiceProduct
from modules.document_extraction.table_engine.models import ColumnType, DetectedColumn
from modules.document_extraction.table_engine.patterns import (
    HEADER_SYNONYMS,
    IGNORED_HEADER_KEYWORDS,
    classify_token,
)

_MULTISPACE_RE = re.compile(r"\s{2,}")
_WORD_RE = re.compile(r"[a-zA-Z]+")

_HEADER_KEYWORD_VOCAB = {
    word
    for synonyms in HEADER_SYNONYMS.values()
    for phrase in synonyms
    for word in phrase.split()
}

_DECIMAL_LIKE_TYPES = (
    ColumnType.PTR, ColumnType.PURCHASE_RATE, ColumnType.MRP,
    ColumnType.AMOUNT, ColumnType.DISCOUNT_AMOUNT,
)


def detect_expected_column_count(rows: List[InvoiceProduct]) -> int:
    """The table's canonical width: the most common token count across all
    rows. Using the mode (not the max) means a handful of ragged/short rows
    don't distort the layout the vast majority of rows actually follow."""
    counts = [len(r.tokens) for r in rows if r.tokens]
    if not counts:
        return 0
    return Counter(counts).most_common(1)[0][0]


def _looks_like_header_line(text: str) -> bool:
    tokens = set(_WORD_RE.findall(text.lower()))
    return len(tokens & _HEADER_KEYWORD_VOCAB) >= 3


def find_header_hint(unassigned_lines: List[str]) -> Optional[List[str]]:
    """Best-effort recovery of the product table's header row. Chunk 6's
    GenericInvoiceParser locates this line to find where the table starts
    but does not keep it structured — it survives verbatim in
    InvoiceDocument.unassigned_lines. If a line there still looks like a
    table header, split it on column gaps (the same 2+-space heuristic the
    parser uses to break a single wide OCR box into cells) to recover
    approximate header cell text, left-to-right. Returns None — never a
    guess — when no such line is found; callers must treat the result as
    optional evidence, not a requirement."""
    for text in unassigned_lines:
        if _looks_like_header_line(text):
            cells = [c for c in _MULTISPACE_RE.split(text.strip()) if c]
            if len(cells) > 1:
                return cells
    return None


def detect_columns(
    rows: List[InvoiceProduct],
    expected_column_count: int,
    header_hint: Optional[List[str]] = None,
) -> List[DetectedColumn]:
    if expected_column_count <= 0:
        return []

    aligned_rows = [r.tokens for r in rows if len(r.tokens) == expected_column_count]
    column_scores = _score_columns_by_pattern(aligned_rows, expected_column_count)
    _apply_header_hint(column_scores, header_hint)
    _apply_neighbour_priors(column_scores)

    assigned_type = _assign_unique_types(column_scores)

    columns: List[DetectedColumn] = []
    for idx in range(expected_column_count):
        ctype = assigned_type.get(idx, ColumnType.UNKNOWN)
        score = column_scores[idx].get(ctype, 0.0)
        header_text = header_hint[idx] if header_hint and idx < len(header_hint) else None
        evidence = [f"pattern:{ctype.value}:{score:.2f}", f"position:{idx}"]
        if header_text:
            evidence.append(f"header:{header_text}")
        columns.append(DetectedColumn(
            column_index=idx, column_type=ctype, header_text=header_text,
            confidence=Confidence(score=round(min(1.0, max(0.0, score)), 4)),
            evidence=evidence,
        ))

    if not any(c.column_type == ColumnType.PRODUCT_NAME for c in columns):
        _fallback_assign_product_name(columns, aligned_rows)

    return columns


def _score_columns_by_pattern(
    aligned_rows: List[List[str]], expected_column_count: int,
) -> List[Dict[ColumnType, float]]:
    column_scores: List[Dict[ColumnType, float]] = []
    for idx in range(expected_column_count):
        agg: Dict[ColumnType, List[float]] = defaultdict(list)
        for tokens in aligned_rows:
            for ctype, score in classify_token(tokens[idx]).items():
                agg[ctype].append(score)
        column_scores.append({ctype: sum(v) / len(v) for ctype, v in agg.items() if v})
    return column_scores


_IGNORED = "IGNORED"


def _best_header_match(header_text: str):
    """Most-specific (longest) matching phrase wins — e.g. "gst base"
    (ignored: a taxable-amount column) must beat the generic "gst"
    substring it also contains (which would otherwise misroute it to
    ColumnType.GST_PERCENT), and "hsn code" must beat a bare "code" ignored
    keyword. Returns a ColumnType, the _IGNORED sentinel, or None (no
    header vocabulary recognized this text at all)."""
    candidates: List[Tuple[int, object]] = []
    for ctype, synonyms in HEADER_SYNONYMS.items():
        for synonym in synonyms:
            if synonym in header_text:
                candidates.append((len(synonym), ctype))
    for keyword in IGNORED_HEADER_KEYWORDS:
        if keyword in header_text:
            candidates.append((len(keyword), _IGNORED))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def _apply_header_hint(
    column_scores: List[Dict[ColumnType, float]], header_hint: Optional[List[str]],
) -> None:
    if not header_hint:
        return
    for idx, scores in enumerate(column_scores):
        if idx >= len(header_hint):
            break
        header_text = header_hint[idx].lower()
        match = _best_header_match(header_text)
        if match is None:
            continue
        if match == _IGNORED:
            # A recognized-but-unmapped column (Taxable/GST-Base amount, an
            # internal Loc/Code cell, ...) — clear any pattern-only
            # candidacy so it resolves to UNKNOWN instead of being forced
            # onto the nearest similarly-shaped real field (e.g. a decimal
            # Taxable-amount column landing on Purchase Rate purely because
            # no better decimal candidate was left).
            scores.clear()
        else:
            # A real header-label match is strong evidence on its own —
            # guarantee it a dominant floor rather than a flat additive, so
            # it reliably outweighs an unrelated column's incidental
            # pattern coincidence (e.g. a short alpha-only unit cell
            # outscoring the real, header-confirmed Product Name column on
            # pattern alone).
            scores[match] = min(1.0, max(scores.get(match, 0.0) + 0.4, 0.75))


def _apply_neighbour_priors(column_scores: List[Dict[ColumnType, float]]) -> None:
    n = len(column_scores)
    for idx in range(n - 1):
        scores, next_scores = column_scores[idx], column_scores[idx + 1]
        if scores.get(ColumnType.QTY, 0.0) > 0.4 and ColumnType.FREE_QTY in next_scores:
            next_scores[ColumnType.FREE_QTY] = min(1.0, next_scores[ColumnType.FREE_QTY] + 0.15)
        if (
            scores.get(ColumnType.PTR, 0.0) > 0.3 or scores.get(ColumnType.PURCHASE_RATE, 0.0) > 0.3
        ) and ColumnType.MRP in next_scores:
            next_scores[ColumnType.MRP] = min(1.0, next_scores[ColumnType.MRP] + 0.1)

    decimal_cols = [
        idx for idx, scores in enumerate(column_scores)
        if any(scores.get(t, 0.0) > 0.3 for t in _DECIMAL_LIKE_TYPES)
    ]
    if decimal_cols:
        last = decimal_cols[-1]
        column_scores[last][ColumnType.AMOUNT] = min(
            1.0, column_scores[last].get(ColumnType.AMOUNT, 0.0) + 0.2,
        )

    if column_scores and column_scores[0].get(ColumnType.SERIAL_NO, 0.0) > 0.0:
        column_scores[0][ColumnType.SERIAL_NO] = min(
            1.0, column_scores[0][ColumnType.SERIAL_NO] + 0.3,
        )


def _assign_unique_types(
    column_scores: List[Dict[ColumnType, float]],
) -> Dict[int, ColumnType]:
    candidates: List[Tuple[float, int, ColumnType]] = [
        (score, idx, ctype)
        for idx, scores in enumerate(column_scores)
        for ctype, score in scores.items()
    ]
    candidates.sort(key=lambda c: c[0], reverse=True)

    assigned: Dict[int, ColumnType] = {}
    used_types: set = set()
    for score, idx, ctype in candidates:
        if idx in assigned or ctype in used_types:
            continue
        assigned[idx] = ctype
        used_types.add(ctype)
    return assigned


def _fallback_assign_product_name(
    columns: List[DetectedColumn], aligned_rows: List[List[str]],
) -> None:
    """Every invoice product table has a product name column — if pattern
    scoring didn't confidently claim one (e.g. a badly OCR'd or unusually
    formatted description column), reassign whichever column is least
    numeric/most alpha-heavy on average, overriding a weak/UNKNOWN
    assignment there rather than leaving the table with no name column at
    all."""
    if not aligned_rows:
        return
    best_idx, best_alpha_ratio = None, -1.0
    for idx, column in enumerate(columns):
        is_strongly_assigned = column.column_type != ColumnType.UNKNOWN and column.confidence.score >= 0.5
        if is_strongly_assigned:
            continue
        ratios = [
            (sum(c.isalpha() for c in row[idx]) / max(1, len(row[idx])))
            for row in aligned_rows if idx < len(row) and row[idx]
        ]
        if not ratios:
            continue
        avg_ratio = sum(ratios) / len(ratios)
        if avg_ratio > best_alpha_ratio:
            best_alpha_ratio, best_idx = avg_ratio, idx
    if best_idx is not None:
        columns[best_idx] = columns[best_idx].model_copy(update={
            "column_type": ColumnType.PRODUCT_NAME,
            "confidence": Confidence(score=max(0.35, columns[best_idx].confidence.score)),
            "evidence": columns[best_idx].evidence + ["fallback:most_alpha_column"],
        })
