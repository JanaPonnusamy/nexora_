"""Chunk 8 — Header Extraction Engine. Data-pattern validators.

Pure regex/heuristic checks — no supplier name, no per-supplier config.
Kept separate from parser/generic_invoice_parser.py's own regexes (even
though a couple, like the GSTIN pattern, are the same well-known national
standard) because this package must never reach into the parser's private
helpers — it only consumes InvoiceDocument, per models.py's docstring.
"""

import re
from datetime import datetime
from typing import Optional

GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$")
DL_NUMBER_RE = re.compile(r"^(?=.*[A-Za-z0-9]{5,})[A-Za-z0-9/.\-\s]{5,25}$")

# Tried in order; the first one that parses the whole string wins. Covers the
# numeric and short/long-month-name layouts seen across supplier invoices —
# never a supplier-specific format.
_DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%b-%y",
    "%b %d, %Y", "%B %d, %Y",
]

# Fractional tolerance used when cross-checking that reported totals
# reconcile with each other (Data Pattern rule — OCR rounding/paise-level
# noise is expected, a genuinely wrong figure is not).
RECONCILE_ABS_TOLERANCE = 1.0
RECONCILE_REL_TOLERANCE = 0.01


def parse_invoice_date(raw: str) -> Optional[str]:
    """Returns the date normalized to ISO-8601 (YYYY-MM-DD), or None if no
    known format matches the whole string."""
    text = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def is_valid_gstin(value: str) -> bool:
    return bool(GSTIN_RE.match(value.strip().upper()))


def is_plausible_dl_number(value: str) -> bool:
    return bool(DL_NUMBER_RE.match(value.strip()))


def values_reconcile(expected: float, actual: float) -> bool:
    diff = abs(expected - actual)
    return diff <= RECONCILE_ABS_TOLERANCE or diff <= abs(expected) * RECONCILE_REL_TOLERANCE
