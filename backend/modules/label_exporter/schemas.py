"""Pydantic response schemas for the Label Exporter module."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


# ---------- Product search ----------


class LabelSearchRow(BaseModel):
    product_code: str
    product_name: str
    unit_description: Optional[str] = None
    current_sublocation: Optional[str] = None
    sale_unit: Optional[float] = None
    mrp: float
    total_stock: float
    sale_days: Optional[float] = None
    purchase_days: Optional[float] = None
    include_label: Optional[str] = None
    remarks: Optional[str] = None
    corrected_unit: Optional[str] = None
    old_unit_description: Optional[str] = None
    assigned_sublocation: Optional[str] = None
    old_sublocation: Optional[str] = None
    assignment_type: Optional[str] = None
    label_required: bool = False


class LabelSearchResult(BaseModel):
    rows: List[LabelSearchRow] = []
    unit_descriptions: List[str] = []
    sublocations: List[str] = []
    last_box_for_letter: Optional[str] = None


# ---------- Box search ----------


class LabelBoxRow(BaseModel):
    box_number: str
    product_count: int
    total_stock: float
    best_sale_days: Optional[float] = None
    best_purchase_days: Optional[float] = None


class BoxSearchResult(BaseModel):
    boxes: List[LabelBoxRow] = []


# ---------- Box products ----------


class LabelBoxProductRow(BaseModel):
    product_code: str
    product_name: str
    unit_description: Optional[str] = None
    mrp: float
    total_stock: float
    sale_days: Optional[float] = None
    purchase_days: Optional[float] = None


class BoxProductResult(BaseModel):
    rows: List[LabelBoxProductRow] = []


# ---------- Batch detail ----------


class LabelBatchRow(BaseModel):
    product_code: str
    batch_code: str
    stock: float
    expiry_date: Optional[str] = None
    mrp: float
    sale_days: Optional[float] = None
    purchase_days: Optional[float] = None
    is_expired: bool = False


class ProductBatchResult(BaseModel):
    rows: List[LabelBatchRow] = []


# ---------- Review (Y/N + remarks) ----------


class LabelReviewUpdateRequest(BaseModel):
    include_label: Optional[str] = None
    remarks: Optional[str] = None


class LabelBulkReviewRequest(BaseModel):
    product_codes: List[str] = []
    include_label: str


# ---------- Sublocation assignment (super admin) ----------


class LabelSublocationAssignRequest(BaseModel):
    sublocation: str = ""


# ---------- Product trend panel ----------


class LabelTrendRow(BaseModel):
    month: str
    sale_qty: float
    purchase_qty: float
    stock_in_hand: float


class LabelTrendResult(BaseModel):
    rows: List[LabelTrendRow] = []


# ---------- Purchase / sales intelligence panels ----------


class LabelPurchaseRow(BaseModel):
    stock: float
    free_qty: float
    discount_pct: float
    item_cost: float
    ptr: float
    mrp: float
    grn_date: Optional[str] = None
    supplier_name: Optional[str] = None


class LabelPurchaseResult(BaseModel):
    rows: List[LabelPurchaseRow] = []


class LabelSaleRow(BaseModel):
    qty: float
    bill_time: Optional[str] = None
    salesman: Optional[str] = None
    customer: Optional[str] = None
    discount_pct: float
    mrp: float


class LabelSaleResult(BaseModel):
    rows: List[LabelSaleRow] = []


# ---------- Unit correction ----------


class LabelUnitCorrectionRequest(BaseModel):
    unit_description: str
    current_unit: Optional[str] = None


# ---------- Location assignment (preview + commit) ----------


class LabelAssignRequest(BaseModel):
    unit: str = ""
    mode: str = "continue"            # continue / new_label / single
    assignment_type: str = "standard_box"  # standard_box / single_product_box
    letter: str = ""
    product_codes: List[str] = []
    start_number: int = 1


class LabelAssignBox(BaseModel):
    box: str
    existing: int = 0
    added: int = 0
    total: int = 0
    capacity: Optional[int] = None


class LabelAssignEntry(BaseModel):
    product_code: str
    product_name: str
    box: str
    slot: int


class LabelAssignResult(BaseModel):
    unit: str
    mode: str
    assignment_type: str
    assignments: List[LabelAssignEntry] = []
    boxes: List[LabelAssignBox] = []
    assigned_count: int = 0
    committed: bool = False


# ---------- Label queue ----------


class LabelQueueRow(BaseModel):
    product_code: str
    product_name: str
    location: Optional[str] = None
    unit_description: Optional[str] = None
    mrp: float = 0
    sale_unit: Optional[float] = None
    assignment_type: Optional[str] = None
    assigned_at: Optional[str] = None
    label_created_at: Optional[str] = None


class LabelQueueResult(BaseModel):
    rows: List[LabelQueueRow] = []


class LabelMarkPrintedRequest(BaseModel):
    product_codes: List[str] = []
