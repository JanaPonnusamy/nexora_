"""Request/response models for the Supplier Rate Engine."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class LowestRateRow(BaseModel):
    product_code: Optional[str] = None
    product_name: str
    pack: Optional[str] = None
    cost: float
    rate_date: Optional[date] = None
    store: Optional[str] = None
    supplier: str
    window: str  # "45d" | "last_bill"


class LowestRateListResponse(BaseModel):
    source_files: List[str]
    window: str
    rows: List[LowestRateRow]
    generated_at: str


class MonthLoss(BaseModel):
    ym: str  # YYYY-MM
    store: str
    qty: float
    loss: float


class ProductLoss(BaseModel):
    product_code: Optional[str] = None
    product_name: str
    total_loss: float
    by_store: dict
    by_month: List[MonthLoss]


class BillLossRow(BaseModel):
    bill_no: Optional[str] = None
    grn_date: Optional[date] = None
    store: str
    product_code: Optional[str] = None
    product_name: str
    qty: float
    actual_cost: float
    benchmark_cost: float
    loss: float


class TenantLossReport(BaseModel):
    tenant: str
    baseline: str  # "4_supplier" | "nathan_actual"
    period_start: str
    period_end: str
    ytd_total_loss: float
    ytd_by_store: dict
    monthwise: List[MonthLoss]
    top_products: List[ProductLoss]
    generated_at: str
