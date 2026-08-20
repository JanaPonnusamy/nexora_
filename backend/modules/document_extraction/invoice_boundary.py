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
A page joins whichever existing group its fingerprint matches, ANYWHERE in
the batch -- not just the group its neighbours are in. Photographed pages
routinely arrive out of order (page 3 shot first, page 1 last), so an
adjacency-only rule would split one invoice into several imports purely
because of the order the files were picked in the file dialog. Pages with
no detectable fingerprint (a genuine continuation page that doesn't
reprint its header) stay with the previous page's group rather than
forcing a split. "Close match" (via difflib, not exact equality) absorbs
ordinary OCR noise between repeated printings of the same invoice number
-- an exact-match rule would false-split on nothing more than one misread
character.

detect_page_sequence() reads the printed "Page No: 2/3" marker, which lets
the pages of one invoice be put back into PRINTED order regardless of the
order they were uploaded in -- product rows are concatenated in that order
(see page_merge.py).
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

# "Page No: 2/3", "Page No.2 / 3", "Page 2 of 3" — the index and the total
# must BOTH be printed (see detect_page_sequence).
_PAGE_MARKER_RE = re.compile(r"page\s*(?:no\.?|#)?\s*:?\s*(\d{1,3})\s*(?:/|of)\s*(\d{1,3})", re.IGNORECASE)


def detect_invoice_groups(document: OCRDocument) -> List[List[int]]:
    """Returns page numbers grouped into likely-separate invoices, e.g.
    [[1, 3, 4], [2]]. Always returns at least one group covering every
    page, every page in exactly one group; a single-group result means no
    split is needed. Groups come back in order of their first page, so the
    group holding page 1 is always groups[0] (service.py keeps that one on
    the original import and splits the rest off)."""
    groups: List[dict] = []
    previous: Optional[dict] = None

    for page in document.pages:
        fingerprint = _page_fingerprint(page)
        if fingerprint is None:
            # A continuation page that doesn't reprint its invoice number:
            # it belongs with the page before it, and if it IS the first
            # page it starts a group of its own.
            target = previous or _new_group(groups, None)
        else:
            target = next(
                (g for g in groups if g["fingerprint"] and _same_invoice(fingerprint, g["fingerprint"])),
                None,
            ) or _new_group(groups, fingerprint)
        target["pages"].append(page.page_no)
        previous = target

    return [sorted(g["pages"]) for g in groups]


def _new_group(groups: List[dict], fingerprint: Optional[str]) -> dict:
    group = {"fingerprint": fingerprint, "pages": []}
    groups.append(group)
    return group


def detect_page_sequence(page: OCRPage) -> Optional[int]:
    """The printed page index from a "Page No: 2/3" / "Page 2 of 3" marker,
    or None if the page doesn't print one. Only the index is returned — the
    total is used solely to confirm the marker really is a page marker (a
    bare "Page 2" with no total is too easy to confuse with a stray
    number)."""
    for line in page.lines:
        match = _PAGE_MARKER_RE.search(line.text)
        if match:
            return int(match.group(1))
    return None


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
