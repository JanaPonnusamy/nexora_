"""Chunk 7 — Product Table Understanding Engine. Output models.

StructuredProductRow is the ONLY shape this engine produces. It is a pure
transform target: InvoiceDocument.products (List[InvoiceProduct], with each
row's `tokens` / `ocr_row_text` / `region` bounding box) in,
StructuredProductRow out (table_understanding_engine.py).

Per the chunk brief, this engine never:
  * writes a database
  * resolves a ProductCode
  * calls a repository
  * searches SupplierProductMapping
That remains Chunk 9 (Product Extraction)'s job, applied on top of this
engine's output.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel

from modules.document_extraction.ocr.models import BoundingBox, Confidence


class ColumnType(str, Enum):
    SERIAL_NO = "SERIAL_NO"
    PRODUCT_NAME = "PRODUCT_NAME"
    PACK = "PACK"
    HSN = "HSN"
    BATCH = "BATCH"
    EXPIRY = "EXPIRY"
    QTY = "QTY"
    FREE_QTY = "FREE_QTY"
    PTR = "PTR"
    PURCHASE_RATE = "PURCHASE_RATE"
    MRP = "MRP"
    GST_PERCENT = "GST_PERCENT"
    DISCOUNT_PERCENT = "DISCOUNT_PERCENT"
    DISCOUNT_AMOUNT = "DISCOUNT_AMOUNT"
    AMOUNT = "AMOUNT"
    # Detected but never written to a StructuredProductRow field. Columns
    # like a supplier's internal "Loc"/"Code" or an S.U (unit-of-sale) cell
    # still need to be *detected* so their tokens don't get misaligned onto
    # a real output column — they just have no canonical home in the
    # OUTPUT FIELDS list.
    UNKNOWN = "UNKNOWN"


# The 13 canonical business fields from the chunk's OUTPUT FIELDS list
# (everything except Confidence, which lives on StructuredProductRow
# itself, not as a column). SERIAL_NO, DISCOUNT_AMOUNT and UNKNOWN are real
# ColumnTypes so the detector/aligner can recognize and quarantine those
# cells, but they are deliberately excluded here — a column detected as one
# of them is never "missing" from a row and never populates a field.
OUTPUT_COLUMN_TYPES = {
    ColumnType.PRODUCT_NAME, ColumnType.PACK, ColumnType.HSN, ColumnType.BATCH,
    ColumnType.EXPIRY, ColumnType.QTY, ColumnType.FREE_QTY, ColumnType.PTR,
    ColumnType.PURCHASE_RATE, ColumnType.MRP, ColumnType.GST_PERCENT,
    ColumnType.DISCOUNT_PERCENT, ColumnType.AMOUNT,
}


class DetectedColumn(BaseModel):
    """One column of the detected table layout, kept for traceability/
    debugging — the same role PageRegion plays for the parser layer. Every
    StructuredProductRow field can be traced back to the DetectedColumn
    that produced it."""
    column_index: int
    column_type: ColumnType
    header_text: Optional[str] = None
    confidence: Confidence
    evidence: List[str] = []


class RowIssue(BaseModel):
    code: str
    detail: str


class StructuredProductRow(BaseModel):
    line_number: int
    ocr_row_text: str
    product_name: Optional[str] = None
    pack: Optional[str] = None
    hsn: Optional[str] = None
    batch: Optional[str] = None
    expiry: Optional[str] = None
    qty: Optional[float] = None
    free_qty: Optional[float] = None
    ptr: Optional[float] = None
    purchase_rate: Optional[float] = None
    mrp: Optional[float] = None
    gst_percent: Optional[float] = None
    discount_percent: Optional[float] = None
    amount: Optional[float] = None
    confidence: Confidence = Confidence(score=0.0)
    column_confidence: Dict[str, float] = {}
    missing_columns: List[str] = []
    ambiguous_columns: List[str] = []
    issues: List[RowIssue] = []
    bbox: Optional[BoundingBox] = None


class TableLayout(BaseModel):
    """Whole-table detection result, kept alongside the row list so a
    caller (Chunk 9, a future Review UI debug panel) can see how columns
    were identified without re-running detection."""
    expected_column_count: int
    columns: List[DetectedColumn]
    header_source: Optional[str] = None  # "header_row" | "position_and_pattern" | None
    row_count: int


class TableUnderstandingResult(BaseModel):
    layout: TableLayout
    rows: List[StructuredProductRow]
