"""Chunk 7 — Product Table Understanding Engine. Data-pattern classifier.

Pure regex/heuristic token classification — no supplier name, no per-
supplier config, nothing hardcoded to a specific invoice layout. Every
score here is a *plausibility* signal for one token in isolation; resolving
which single ColumnType a whole column actually is happens one layer up in
column_detector.py, which combines this with header text, position, and
neighbour-column priors.

HEADER_SYNONYMS is the generic column-header vocabulary named in the chunk
brief (Description/Medicine/Item/Product -> Product Name, etc.). Note the
brief's own worked example folds "PTR" into the same target as "Trade Rate"
/"Purchase Rate" — but the OUTPUT FIELDS list carries PTR and Purchase Rate
as two separate fields, so that example is read here as illustrative of the
general "many header labels -> one canonical column" idea rather than a
literal rule: "ptr" maps only to ColumnType.PTR, "trade rate"/"purchase
rate"/"rate" map only to ColumnType.PURCHASE_RATE.
"""

import re
from typing import Dict, List

from modules.document_extraction.table_engine.models import ColumnType

HEADER_SYNONYMS: Dict[ColumnType, List[str]] = {
    ColumnType.SERIAL_NO: ["s no", "sno", "sl no", "s.no", "serial"],
    ColumnType.PRODUCT_NAME: [
        "description", "medicine", "item", "product", "particular",
        "particulars", "product name", "drug",
    ],
    ColumnType.PACK: ["pack", "packing"],
    ColumnType.HSN: ["hsn", "sac", "hsn/sac", "hsn code"],
    ColumnType.BATCH: ["batch", "batch no", "batchno", "batch number"],
    ColumnType.EXPIRY: ["exp", "expiry", "exp date", "expiry date"],
    ColumnType.QTY: ["qty", "quantity"],
    ColumnType.FREE_QTY: ["free", "scheme", "bonus", "fr", "free qty"],
    ColumnType.PTR: ["ptr"],
    ColumnType.PURCHASE_RATE: ["purchase rate", "trade rate", "trade price", "rate"],
    ColumnType.MRP: ["mrp"],
    ColumnType.GST_PERCENT: ["gst", "gst%", "gst %", "tax"],
    ColumnType.DISCOUNT_PERCENT: [
        "disc", "discount", "disc%", "sch disc", "cash disc", "pdis", "scheme disc",
    ],
    ColumnType.DISCOUNT_AMOUNT: ["discount amount", "disc amt"],
    ColumnType.AMOUNT: ["amount", "total", "value", "product value", "net amount"],
}

# Column labels real supplier tables commonly carry that have no home in
# the OUTPUT FIELDS list (a taxable/GST-base amount, a location/internal
# code, a unit-of-sale cell — Sample A's own "GST Base"/"S.U" columns are
# real examples, see Document_Extraction_Design.md §3). A header match here
# forces the column to ColumnType.UNKNOWN outright, so it never gets
# shoehorned into a real money field (e.g. a Taxable/GST-Base column being
# forced onto Purchase Rate just because both are decimal-shaped) purely
# for lack of a better-scoring candidate.
IGNORED_HEADER_KEYWORDS = [
    "taxable", "gst base", "basic amount", "basic rate", "loc", "location",
    "code", "s.u", "unit", "pending order",
]

_GST_SLABS = {0.0, 5.0, 12.0, 18.0, 28.0}

_EXPIRY_RE = re.compile(r"^(0?[1-9]|1[0-2])[/\-](\d{2}|\d{4})$")
_INTEGER_RE = re.compile(r"^\d{1,6}$")
_DECIMAL_RE = re.compile(r"^\d{1,3}(,\d{2,3})*(\.\d{1,4})?$")
_HSN_RE = re.compile(r"^\d{4,8}$")
_BATCH_RE = re.compile(r"^(?=[A-Za-z0-9\-/]{3,15}$)(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9\-/]+$")
_PACK_RE = re.compile(
    r"(\d+\s*[xX*]\s*\d+)|(\d+\s*(ML|MG|GM|KG|MCG|TAB|CAP|BOT|VIAL|AMP|SACHET))",
    re.IGNORECASE,
)
_PACK_MAX_LEN = 15


def classify_token(token: str) -> Dict[ColumnType, float]:
    """Pattern-match score (0..1) for each ColumnType this single token
    could plausibly belong to. A token routinely scores against several
    types (e.g. "12" matches Qty, Free Qty and Serial No all at once) —
    that ambiguity is expected and resolved by column-level aggregation,
    not here."""
    scores: Dict[ColumnType, float] = {}
    text = token.strip()
    if not text:
        return scores

    if _EXPIRY_RE.match(text):
        scores[ColumnType.EXPIRY] = 0.95

    is_percent_sign = text.endswith("%")
    numeric_clean = text.replace(",", "").rstrip("%").strip()

    if _HSN_RE.match(text):
        # Independent of the QTY/SERIAL_NO checks below: HSN/SAC codes run
        # 4-8 digits, well past the length a real quantity or serial number
        # cell would ever use, so a 7-8 digit code must not fall through to
        # those just because it also happens to satisfy _INTEGER_RE.
        scores[ColumnType.HSN] = 0.55

    if _INTEGER_RE.match(text):
        as_int = int(text)
        if len(text) <= 4 and as_int <= 9999:
            scores[ColumnType.QTY] = 0.55
            scores[ColumnType.FREE_QTY] = 0.45
        if as_int <= 999:
            scores[ColumnType.SERIAL_NO] = 0.3

    if _DECIMAL_RE.match(numeric_clean):
        value = _safe_float(numeric_clean)
        if value is not None:
            if is_percent_sign or 0 <= value <= 100:
                base = 0.5
                if round(value, 1) in _GST_SLABS or round(value) in _GST_SLABS:
                    base = 0.8
                scores[ColumnType.GST_PERCENT] = max(
                    scores.get(ColumnType.GST_PERCENT, 0.0),
                    base if value <= 28.5 else 0.3,
                )
                scores[ColumnType.DISCOUNT_PERCENT] = max(
                    scores.get(ColumnType.DISCOUNT_PERCENT, 0.0), 0.45,
                )
            if "." in numeric_clean or value > 100 or not is_percent_sign:
                for ctype in (
                    ColumnType.PTR, ColumnType.PURCHASE_RATE, ColumnType.MRP,
                    ColumnType.AMOUNT,
                ):
                    scores[ctype] = max(scores.get(ctype, 0.0), 0.4)
                scores[ColumnType.DISCOUNT_AMOUNT] = max(
                    scores.get(ColumnType.DISCOUNT_AMOUNT, 0.0), 0.25,
                )

    if _BATCH_RE.match(text):
        scores[ColumnType.BATCH] = max(scores.get(ColumnType.BATCH, 0.0), 0.6)

    if len(text) <= _PACK_MAX_LEN and _PACK_RE.search(text):
        # Length-gated: a pack cell ("10*10", "1X100ML") is short. Without
        # the gate, this regex also fires on a dosage string embedded deep
        # inside a long product-name cell ("PARACETAMOL 500MG TAB"), which
        # would wrongly pull Pack-column evidence onto the Product Name
        # column.
        scores[ColumnType.PACK] = max(scores.get(ColumnType.PACK, 0.0), 0.6)

    alpha_chars = sum(c.isalpha() for c in text)
    non_space_chars = len(text.replace(" ", "")) or 1
    alpha_ratio = alpha_chars / non_space_chars
    if alpha_ratio >= 0.55 and len(text) >= 4 and text[0].isalpha():
        # Deliberately tolerant of embedded digits (dosages like "500MG",
        # "10MG") — a real medicine name is majority letters, not *only*
        # letters. Longer, multi-word cells score higher: a genuine
        # description ("PARACETAMOL 500MG TAB") should clearly outscore an
        # incidental short alpha-only unit/word cell ("STRIP", "TAB") that
        # happens to share a column with no real pattern signal of its own.
        word_bonus = 0.15 if len(text.split()) >= 2 else 0.0
        length_bonus = min(len(text), 40) / 100
        scores[ColumnType.PRODUCT_NAME] = max(
            scores.get(ColumnType.PRODUCT_NAME, 0.0),
            min(0.9, 0.3 + length_bonus + word_bonus),
        )

    return scores


def _safe_float(text: str):
    try:
        return float(text)
    except ValueError:
        return None
