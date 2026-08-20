"""Page-by-page extraction, then merge into one invoice.

Everything reaching this module is already known to be ONE invoice's pages
(invoice_boundary split any others off first — see service.run_ocr). What's
left is that a multi-page invoice must not be parsed as one long document.

GenericInvoiceParser's header/totals rules are "first labelled line in the
document wins", and the table engine detects its column layout once. That is
correct for a single page and wrong across several: a dot-matrix invoice
reprints its full header and footer on every page, each page's product table
starts at a slightly different x-offset, and the pages arrive in whatever
order they were photographed in. Parsed as one document, page 2's reprinted
"Page No" label or address line can win a header field over page 1's real
value, which is how supplier_name ended up as an address line and
invoice_number as the literal text "&Page No Bill Date".

So: parse and extract each page independently (each page gets its own column
detection, its own header read), then merge — header fields by majority vote
across pages (the same value printed on 3 of 3 pages beats a one-page OCR
misread), product rows concatenated in PRINTED page order (invoice_boundary.
detect_page_sequence, not upload order). Header extraction/validation/
reconciliation itself still runs exactly once, on the merged document, so
there is only ever one place those rules live (header_engine).
"""

import logging
from collections import Counter
from typing import List, Optional

from pydantic import BaseModel

from modules.document_extraction.invoice_boundary import detect_page_sequence
from modules.document_extraction.ocr.models import OCRDocument
from modules.document_extraction.parser.models import (
    InvoiceDocument,
    InvoiceHeader,
    InvoiceTotals,
    SupplierBlock,
)
from modules.document_extraction.parser.parser_factory import ParserFactory
from modules.document_extraction.table_engine import TableUnderstandingEngine
from modules.document_extraction.table_engine.models import StructuredProductRow

logger = logging.getLogger("document_extraction.page_merge")


class PageExtraction(BaseModel):
    """One page's own parse + table read, before any merging."""
    page_no: int
    printed_page_no: Optional[int] = None
    document: InvoiceDocument
    rows: List[StructuredProductRow] = []

    @property
    def order_key(self) -> tuple:
        # Pages that print a "Page 2/3" marker are ordered by it; pages that
        # don't fall back to upload order, and sort after the marked ones so
        # a partially-marked invoice still keeps its known pages in sequence.
        return (0, self.printed_page_no) if self.printed_page_no else (1, self.page_no)


def extract_pages(ocr_document: OCRDocument) -> List[PageExtraction]:
    """Parses + reads the product table of each page on its own, in printed
    page order (see PageExtraction.order_key)."""
    parser = ParserFactory.create()
    table_engine = TableUnderstandingEngine()

    extractions = []
    for page in ocr_document.pages:
        single_page = ocr_document.model_copy(update={"pages": [page]})
        document = parser.parse(single_page)
        extractions.append(PageExtraction(
            page_no=page.page_no,
            printed_page_no=detect_page_sequence(page),
            document=document,
            rows=table_engine.understand(document).rows,
        ))

    extractions.sort(key=lambda e: e.order_key)
    return extractions


def merge_document(pages: List[PageExtraction], ocr_document: OCRDocument) -> InvoiceDocument:
    """One InvoiceDocument standing in for the whole invoice, built field by
    field from the per-page parses. Downstream (header_engine,
    supplier_engine) is unchanged — it still sees a single InvoiceDocument."""
    documents = [p.document for p in pages]
    base = documents[0]

    merged = base.model_copy(update={
        "metadata": base.metadata.model_copy(update={"page_count": len(ocr_document.pages)}),
        "supplier_block": _best_supplier_block(documents),
        "header": _merge_model(InvoiceHeader, [d.header for d in documents]),
        "totals": _merge_model(InvoiceTotals, [d.totals for d in documents]),
        # GST slab tables aren't merged across pages: each page reprints the
        # WHOLE slab summary, so concatenating would double every slab and
        # break header_engine's GST_SUMMARY_TOTALS_MISMATCH reconciliation.
        # The most complete single printing of it is the one to keep.
        "gst_summary": max((d.gst_summary for d in documents), key=len, default=[]),
        "products": [p for d in documents for p in d.products],
        "regions": [r for d in documents for r in d.regions],
        "footer_text": next((d.footer_text for d in documents if d.footer_text), None),
        "unassigned_lines": [line for d in documents for line in d.unassigned_lines],
    })
    return merged


def merge_rows(pages: List[PageExtraction]) -> List[StructuredProductRow]:
    """Every page's product rows, in printed page order, renumbered 1..N.

    A row whose identity (product + batch + qty + amount) already appeared is
    dropped: pages photographed twice, or a page that reprints the previous
    page's last row as a carry-over line, would otherwise import the same
    stock line twice. Rows with no product name at all are never treated as
    duplicates of each other — they carry no identity to compare."""
    merged: List[StructuredProductRow] = []
    seen = set()
    for page in pages:
        for row in page.rows:
            identity = _row_identity(row)
            if identity is not None and identity in seen:
                logger.info(
                    "document_extraction.page_merge dropped duplicate row page=%s product=%r",
                    page.page_no, row.product_name,
                )
                continue
            if identity is not None:
                seen.add(identity)
            merged.append(row.model_copy(update={"line_number": len(merged) + 1}))
    return merged


def _row_identity(row: StructuredProductRow):
    if not row.product_name:
        return None
    return (row.product_name.strip().upper(), (row.batch or "").strip().upper(), row.qty, row.amount)


def _merge_model(model_class, instances):
    """Field-by-field majority vote across the pages that printed a value for
    that field. Ties (including the ordinary 2-page case where each page says
    something different) go to the earliest page, which is the page most
    likely to carry the real header."""
    merged = model_class()
    for field_name in model_class.model_fields:
        values = [getattr(inst, field_name) for inst in instances]
        winner = _majority(values)
        if winner is not None:
            setattr(merged, field_name, winner)
    return merged


def _majority(values):
    present = [v for v in values if v is not None and v != ""]
    if not present:
        return None
    counts = Counter(present)
    best_count = max(counts.values())
    # Counter preserves insertion order among equal counts, so the earliest
    # page wins a tie.
    return next(v for v in counts if counts[v] == best_count)


def _best_supplier_block(documents) -> Optional[SupplierBlock]:
    """The supplier letterhead is only printed properly on some pages — and
    on a reprinted-header page the parser can latch onto an address line as
    the "name". Score each page's block and keep the strongest rather than
    trusting the first page that produced one."""
    blocks = [d.supplier_block for d in documents if d.supplier_block]
    if not blocks:
        return None
    return max(blocks, key=_supplier_block_score)


def _supplier_block_score(block: SupplierBlock) -> int:
    score = 0
    if block.candidate_gst_number:
        score += 4
    if block.candidate_dl_number:
        score += 2
    if block.candidate_phone:
        score += 1
    name = (block.candidate_name or "").strip()
    if name:
        score += 1
        # A supplier name that opens with a digit ("29, Ground Floor, ...")
        # or a door/street word is an address line the parser mistook for the
        # letterhead's name — real enough to keep as a fallback, not good
        # enough to beat a block that read a proper name.
        if not name[0].isdigit() and not _looks_like_address(name):
            score += 2
    return score


_ADDRESS_WORDS = ("road", "street", "floor", "nagar", "cross", "layout", "door no", "plot")


def _looks_like_address(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in _ADDRESS_WORDS)
