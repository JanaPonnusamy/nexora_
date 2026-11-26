from typing import List, Optional

from pydantic import BaseModel


class StockCheckRow(BaseModel):
    product_code: Optional[str] = None
    sublocation: Optional[str] = None
    product_name: Optional[str] = None
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    unit_description: Optional[str] = None
    total_stock: float = 0
    batch_stock: float = 0
    expiry_date: Optional[str] = None
    mrp: float = 0
    sale_unit: Optional[str] = None
    batch_code: Optional[str] = None
    purchase_days: Optional[int] = None
    sale_days: Optional[int] = None


class StockCheckResult(BaseModel):
    rows: List[StockCheckRow] = []


class StockCheckQuery(BaseModel):
    sublocation_from: Optional[str] = None
    sublocation_to: Optional[str] = None
    product_code_from: Optional[int] = None
    product_code_to: Optional[int] = None
    product_name: Optional[str] = None
    supplier_code: Optional[str] = None
    unit_description: Optional[str] = None
    batch_code: Optional[str] = None
    expiry_from: Optional[str] = None
    expiry_to: Optional[str] = None
    min_stock: Optional[float] = None
    max_stock: Optional[float] = None
    include_zero_stock: bool = False
    include_negative_stock: bool = False


class SupplierOption(BaseModel):
    supplier_code: str
    supplier_name: Optional[str] = None
