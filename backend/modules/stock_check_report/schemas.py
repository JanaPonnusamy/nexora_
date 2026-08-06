from typing import List, Optional

from pydantic import BaseModel


class StockCheckRow(BaseModel):
    product_code: Optional[str] = None
    sublocation: Optional[str] = None
    product_name: Optional[str] = None
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
