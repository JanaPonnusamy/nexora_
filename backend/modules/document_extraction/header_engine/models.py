"""Chunk 8 — Header Extraction Engine. Output models.

ExtractedHeader is the ONLY shape this engine produces. It is a pure
transform target: InvoiceDocument (header/totals/gst_summary/supplier_block,
all populated by Chunk 6's GenericInvoiceParser as an unvalidated best-effort
single pass) in, HeaderExtractionResult out (header_extraction_engine.py).

Per the chunk brief, this engine never:
  * writes a database
  * knows about a specific supplier's layout
  * calls a repository
That remains Chunk 9 (Supplier Identification)'s job, applied on top of this
engine's output.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel

from modules.document_extraction.ocr.models import Confidence


class HeaderIssue(BaseModel):
    code: str
    detail: str


class ExtractedHeader(BaseModel):
    supplier_name: Optional[str] = None
    gst_number: Optional[str] = None
    dl_number: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    invoice_type: Optional[str] = None
    credit_days: Optional[str] = None
    transport: Optional[str] = None
    order_number: Optional[str] = None
    salesman: Optional[str] = None
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
    irn_number: Optional[str] = None
    ack_number: Optional[str] = None
    ack_date: Optional[str] = None
    qr_data: Optional[str] = None


class HeaderExtractionResult(BaseModel):
    header: ExtractedHeader
    confidence: Confidence
    field_confidence: Dict[str, float] = {}
    missing_fields: List[str] = []
    warnings: List[HeaderIssue] = []
