"""Invoice Parser abstraction (pre-Chunk-7). Canonical business models.

InvoiceDocument is the ONLY shape Supplier Detection (Chunk 7), Header
Extraction (Chunk 8), and Product Extraction (Chunk 9) may depend on. None
of those stages ever reads an OCRDocument directly — see
generic_invoice_parser.py, which is the sole place OCRDocument -> parser
models happens.

Reuses BoundingBox/Confidence from ocr.models rather than redefining them —
they're pure geometry/score value types with no OCR-engine-specific
meaning, so there's exactly one definition of each across both layers.

Field-naming note: fields prefixed `candidate_`/`_guess`/`ocr_row_text`/
`tokens` are explicitly UNRESOLVED — raw or best-effort-heuristic values a
generic, supplier-agnostic parser can produce without a supplier's known
layout or a database lookup. Turning a candidate into an authoritative
value (matching a real supplier row, mapping a token list to named
columns, resolving a ProductCode) is Chunk 7/8/9's job, not this layer's.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from modules.document_extraction.ocr.models import BoundingBox, Confidence


class RegionType(str, Enum):
    HEADER = "HEADER"
    SUPPLIER_BLOCK = "SUPPLIER_BLOCK"
    INVOICE_NUMBER = "INVOICE_NUMBER"
    INVOICE_DATE = "INVOICE_DATE"
    PRODUCT_TABLE = "PRODUCT_TABLE"
    GST_SECTION = "GST_SECTION"
    TOTALS = "TOTALS"
    FOOTER = "FOOTER"
    QR_CODE = "QR_CODE"
    UNKNOWN = "UNKNOWN"


class PageRegion(BaseModel):
    """One detected region of interest, kept for traceability/debugging —
    every field value in InvoiceDocument that came from a specific spot on
    the page can be traced back to the OCRLine(s) that produced it via
    line_numbers. Detected from keywords + relative position + bounding
    boxes only — never a hardcoded coordinate (see generic_invoice_parser.py
    module docstring)."""
    region_type: RegionType
    page_no: int
    bbox: BoundingBox
    line_numbers: List[int] = []
    matched_keyword: Optional[str] = None
    confidence: Confidence


class DocumentMetadata(BaseModel):
    ocr_engine_name: str
    ocr_engine_version: Optional[str] = None
    ocr_average_confidence: Optional[float] = None
    page_count: int
    parser_name: str
    parser_version: str
    parsed_at: str  # ISO-8601, set at parse time (pure computation, no DB write)


class SupplierBlock(BaseModel):
    """Everything the parser could read out of the supplier letterhead
    block, unresolved. NOT a supplier match — Chunk 7 (Supplier Detection)
    compares these candidates against the supplier master and decides which
    real supplier (if any) this is."""
    raw_text: str
    candidate_name: Optional[str] = None
    candidate_gst_number: Optional[str] = None
    candidate_dl_number: Optional[str] = None
    candidate_phone: Optional[str] = None
    candidate_address: Optional[str] = None
    region: Optional[PageRegion] = None


class InvoiceHeader(BaseModel):
    """Transactional header fields. Values are the raw text captured next to
    a matching keyword label — not yet type-parsed/validated (e.g.
    invoice_date is still a string, not a date). Chunk 8's supplier-layout-
    driven header extraction is the authoritative pass; this is a generic
    best-effort capture with no per-supplier column knowledge."""
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    invoice_type: Optional[str] = None
    order_number: Optional[str] = None
    transport: Optional[str] = None
    salesman: Optional[str] = None
    credit_days: Optional[str] = None
    irn_number: Optional[str] = None
    ack_number: Optional[str] = None
    ack_date: Optional[str] = None
    qr_data: Optional[str] = None


class InvoiceTotals(BaseModel):
    gross_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    scheme_discount: Optional[float] = None
    cash_discount: Optional[float] = None
    taxable_amount: Optional[float] = None
    cgst_amount: Optional[float] = None
    sgst_amount: Optional[float] = None
    igst_amount: Optional[float] = None
    cess_amount: Optional[float] = None
    round_off: Optional[float] = None
    net_amount: Optional[float] = None
    item_count: Optional[int] = None
    total_quantity: Optional[float] = None


class GSTSummary(BaseModel):
    """One row of the invoice's GST-slab breakup table (e.g. "12% ... 5000
    600 600 -- --")."""
    gst_percent: float
    taxable_amount: Optional[float] = None
    cgst_amount: Optional[float] = None
    sgst_amount: Optional[float] = None
    igst_amount: Optional[float] = None
    cess_amount: Optional[float] = None
    total_amount: Optional[float] = None


class InvoiceProduct(BaseModel):
    """One row of the product table. Only `tokens`/`ocr_row_text` are
    guaranteed populated by GenericInvoiceParser — they are the row's cells
    in left-to-right reading order, unmapped to any named column because a
    generic parser has no supplier-specific layout to map against. The
    named business fields (pack, hsn_code, batch_number, quantity, ...)
    exist here because they are the canonical shape downstream code
    consumes, but a generic parse leaves them None; populating them from
    `tokens` via a supplier's doc_supplier_layout mapping is Chunk 9's job.
    `product_name_guess` is a heuristic (longest non-numeric token) purely
    for human/debug convenience — never treated as a resolved product
    name."""
    line_number: int
    ocr_row_text: str
    tokens: List[str] = []
    product_name_guess: Optional[str] = None
    pack: Optional[str] = None
    hsn_code: Optional[str] = None
    batch_number: Optional[str] = None
    expiry_raw: Optional[str] = None
    quantity: Optional[float] = None
    free_quantity: Optional[float] = None
    ptr: Optional[float] = None
    purchase_rate: Optional[float] = None
    mrp: Optional[float] = None
    gst_percent: Optional[float] = None
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None
    amount: Optional[float] = None
    confidence: Confidence
    region: Optional[PageRegion] = None


class InvoiceDocument(BaseModel):
    """The canonical, engine-agnostic, supplier-agnostic business model.
    Supplier Detection, Header Extraction, and Product Extraction (Chunks
    7-9) consume this and only this — never OCRDocument, never a raw OCR
    engine response."""
    metadata: DocumentMetadata
    regions: List[PageRegion] = []
    supplier_block: Optional[SupplierBlock] = None
    header: InvoiceHeader = InvoiceHeader()
    totals: InvoiceTotals = InvoiceTotals()
    gst_summary: List[GSTSummary] = []
    products: List[InvoiceProduct] = []
    footer_text: Optional[str] = None
    unassigned_lines: List[str] = []
