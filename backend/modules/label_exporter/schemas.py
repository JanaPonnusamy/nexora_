"""Pydantic response schemas for the Label Exporter module."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


# ---------- Product search ----------


class LabelSearchRow(BaseModel):
    product_code: str
    product_name: str
    unit_description: Optional[str] = None
    box_number: Optional[str] = None
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
