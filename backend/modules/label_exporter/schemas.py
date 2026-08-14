from typing import List, Optional

from pydantic import BaseModel


class LabelSearchRow(BaseModel):
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    unit_description: Optional[str] = None
    sale_unit: float = 0
    mrp: float = 0
    total_stock: float = 0
    current_sublocation: Optional[str] = None
    purchase_days: Optional[int] = None
    sale_days: Optional[int] = None
    batch_stock: float = 0


class LabelSearchResult(BaseModel):
    rows: List[LabelSearchRow] = []
    last_box_for_letter: Optional[str] = None
    unit_descriptions: List[str] = []


class BoxRow(BaseModel):
    box_number: str
    product_count: int = 0
    total_stock: float = 0
    best_sale_days: Optional[int] = None
    best_purchase_days: Optional[int] = None


class BoxSearchResult(BaseModel):
    boxes: List[BoxRow] = []


class BoxProductRow(BaseModel):
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    total_stock: float = 0
    sale_days: Optional[int] = None
    purchase_days: Optional[int] = None
    unit_description: Optional[str] = None
    sale_unit: float = 0
    mrp: float = 0


class BoxProductResult(BaseModel):
    rows: List[BoxProductRow] = []


class ProductBatchRow(BaseModel):
    product_code: Optional[str] = None
    batch_code: Optional[str] = None
    stock: float = 0
    expiry_date: Optional[str] = None
    mrp: float = 0
    purchase_days: Optional[int] = None
    sale_days: Optional[int] = None
    is_expired: bool = False


class ProductBatchResult(BaseModel):
    rows: List[ProductBatchRow] = []
