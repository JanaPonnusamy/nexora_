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


class LabelSearchResult(BaseModel):
    rows: List[LabelSearchRow] = []
    unit_descriptions: List[str] = []
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


# ---------- Letter-wise review ----------


class LabelReviewRow(BaseModel):
    product_code: str
    product_name: str
    unit_description: Optional[str] = None
    current_sublocation: Optional[str] = None
    mrp: float
    total_stock: float
    include_label: Optional[str] = None
    product_kind: Optional[str] = None
    suggested_unit_description: Optional[str] = None
    suggestion_status: str = "none"
    final_unit_description: Optional[str] = None


class LabelReviewListResult(BaseModel):
    rows: List[LabelReviewRow] = []


class LabelReviewUpdateRequest(BaseModel):
    include_label: Optional[str] = None
    product_kind: Optional[str] = None
    suggested_unit_description: Optional[str] = None


class LabelSuggestionRow(BaseModel):
    tenant_id: str
    store_id: str
    product_code: str
    product_name: str
    current_unit_description: Optional[str] = None
    suggested_unit_description: Optional[str] = None
    suggested_by: Optional[str] = None
    suggested_at: Optional[str] = None
    suggestion_status: str


class LabelSuggestionListResult(BaseModel):
    rows: List[LabelSuggestionRow] = []


class LabelSuggestionDecisionRequest(BaseModel):
    approved: bool
    final_unit_description: Optional[str] = None
