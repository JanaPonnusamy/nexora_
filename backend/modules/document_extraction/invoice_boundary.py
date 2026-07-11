"""Multi-invoice-per-upload detection.

Multi-page uploads are usually a single invoice's pages, but users
sometimes photograph/scan two unrelated invoices into one batch (e.g. a
purchase invoice's pages 1-3 plus an unrelated bill's page 4). No parser
downstream can produce a coherent header/totals/product-table read on a
mix of two different invoices' data, so that case has to be caught and
split into separate imports BEFORE header/table extraction ever runs --
see service.py's run_ocr, the only caller.

Detection signal: a per-page "fingerprint" -- the invoice/bill number
printed on that page if a labeled one is found, else a GSTIN found
anywhere on the page (weaker: identifies the supplier, not the specific
invoice, but still catches two different suppliers bundled together).
Consecutive pages are grouped together as long as each page's fingerprint
(when it has one) is a close match to the current group's fingerprint;
pages with no detectable fingerprint (a genuine continuation page that
doesn't reprint its header) stay in the current group rather than forcing
a split. "Close match" (via difflib, not exact equality) absorbs ordinary
OCR noise between repeated printings of the same invoice number -- an
exact-match rule would false-split on nothing more than one misread
character.
"""

import difflib
import re
from typing import List, Optional

from modules.document_extraction.ocr.models import OCRDocument, OCRPage

# Matches on the LABEL, tolerant of OCR's inconsistent spacing (e.g. "Tax
# InvNo..." with no space at all, seen on a real sample invoice) -- a
# plain substring check on "inv no" would miss that.
_INVOICE_NUMBER_RE = re.compile(r"(?:tax\s*)?inv(?:oice)?\s*(?:no\.?|number|#)|bill\s*no\.?", re.IGNORECASE)
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b")
_WHITESPACE_RE = re.compile(r"\s+")

# On a multi-column printed header (label and value in separate boxes),
# the value can land several OCR-detected lines away from its label once
# sorted into reading order -- not necessarily the very next line -- so
# the value is found by shape (alnum, has a digit, no spaces) within a
# short lookahead window rather than assumed to be immediately adjacent.
_VALUE_LOOKAHEAD_LINES = 6
_VALUE_SHAPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-/.]{3,19}$")

_FINGERPRINT_SIMILARITY_THRESHOLD = 0.75


def detect_invoice_groups(document: OCRDocument) -> List[List[int]]:
    """Returns page numbers grouped into likely-separate invoices, e.g.
    [[1, 2, 3], [4]]. Always returns at least one group covering every
    page; a single-group result means no split is needed."""
    groups: List[List[int]] = []
    current_group: List[int] = []
    current_fingerprint: Optional[str] = None

    for page in document.pages:
        fingerprint = _page_fingerprint(page)
        if (
            fingerprint is not None
            and current_fingerprint is not None
            and not _same_invoice(fingerprint, current_fingerprint)
        ):
            groups.append(current_group)
            current_group = []
        if fingerprint is not None:
            current_fingerprint = fingerprint
        current_group.append(page.page_no)

    if current_group:
        groups.append(current_group)
    return groups


def _same_invoice(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a, b).ratio() >= _FINGERPRINT_SIMILARITY_THRESHOLD


def _page_fingerprint(page: OCRPage) -> Optional[str]:
    lines = page.lines
    for idx, line in enumerate(lines):
        match = _INVOICE_NUMBER_RE.search(line.text)
        if not match:
            continue
        remainder = line.text[match.end():].strip(" :.-\t")
        if _looks_like_value(remainder):
            return _normalize(remainder)
        for lookahead in lines[idx + 1: idx + 1 + _VALUE_LOOKAHEAD_LINES]:
            candidate = lookahead.text.strip()
            if _looks_like_value(candidate):
                return _normalize(candidate)

    for line in lines:
        gstin = _GSTIN_RE.search(line.text.upper())
        if gstin:
            return gstin.group(0)
    return None


def _looks_like_value(text: str) -> bool:
    return bool(_VALUE_SHAPE_RE.match(text)) and any(c.isdigit() for c in text)


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub("", text).upper()
