"""Pydantic request schemas for the Document Extraction API."""

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class HeaderPatch(BaseModel):
    """Partial update to doc_import's header fields. Every field optional —
    only the ones present in the request body are written."""
    invoice_number: Optional[str] = Field(None, max_length=50)
    invoice_date: Optional[date] = None
    invoice_type: Optional[str] = Field(None, max_length=30)
    order_number: Optional[str] = Field(None, max_length=50)
    transport: Optional[str] = Field(None, max_length=100)
    salesman: Optional[str] = Field(None, max_length=100)
    credit_days: Optional[int] = None
    supplier_name: Optional[str] = Field(None, max_length=200)
    gst_number: Optional[str] = Field(None, max_length=20)
    dl_number: Optional[str] = Field(None, max_length=50)
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
    irn_number: Optional[str] = Field(None, max_length=100)
    ack_number: Optional[str] = Field(None, max_length=50)
    ack_date: Optional[date] = None
    actor: Optional[str] = None


class ItemPatch(BaseModel):
    normalized_product_name: Optional[str] = Field(None, max_length=300)
    pack: Optional[str] = Field(None, max_length=50)
    hsn_code: Optional[str] = Field(None, max_length=20)
    batch_number: Optional[str] = Field(None, max_length=50)
    expiry_raw: Optional[str] = Field(None, max_length=20)
    expiry_date: Optional[date] = None
    quantity: Optional[float] = None
    free_quantity: Optional[float] = None
    ptr: Optional[float] = None
    purchase_rate: Optional[float] = None
    mrp: Optional[float] = None
    gst_percent: Optional[float] = None
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None
    amount: Optional[float] = None
    actor: Optional[str] = None


class SupplierAssignRequest(BaseModel):
    matched_supplier_code: Optional[str] = Field(None, max_length=50)
    supplier_name: Optional[str] = Field(None, max_length=200)
    gst_number: Optional[str] = Field(None, max_length=20)
    dl_number: Optional[str] = Field(None, max_length=50)
    actor: Optional[str] = None


class SaveRequest(BaseModel):
    force: bool = False
    actor: Optional[str] = None


class ExportRequest(BaseModel):
    import_ids: List[int] = Field(..., min_length=1)
    file_format: str = Field("xlsx", pattern="^(xlsx|csv)$")
    actor: Optional[str] = None


class ReprocessRequest(BaseModel):
    from_stage: str = Field(..., pattern="^(preprocessing|ocr|extraction|validation)$")
    actor: Optional[str] = None


class SupplierLayoutUpsert(BaseModel):
    layout_id: Optional[int] = None
    supplier_code: Optional[str] = Field(None, max_length=50)
    layout_name: str = Field(..., max_length=150)
    layout_json: Dict[str, Any]
    actor: Optional[str] = None
