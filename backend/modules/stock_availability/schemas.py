"""Response shapes for the Stock Availability module (documentation / typing).

The endpoints return plain dicts shaped by the service layer; these Pydantic
models describe that contract for OpenAPI and keep the front-end types honest.
"""

from typing import List, Optional

from pydantic import BaseModel


class ProductRow(BaseModel):
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    sale_unit: Optional[str] = None
    stock: float = 0
    mrp: float = 0
    batch_no: Optional[str] = None


class BranchCard(BaseModel):
    store_id: str
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    total_stock: float = 0
    matching_count: int = 0
    products: List[ProductRow] = []


class SearchSummary(BaseModel):
    total_stores: int = 0
    total_products_found: int = 0
    stores_with_stock: int = 0
    total_stock_all_stores: float = 0


class SearchResult(BaseModel):
    stores: List[BranchCard] = []
    summary: SearchSummary


class CoreBulkItem(BaseModel):
    store_id: str
    product_code: str


class CoreBulkRequest(BaseModel):
    tenant_id: str
    months: int = 3
    items: List[CoreBulkItem] = []


class SalesOrderIgnoreUpdate(BaseModel):
    tenant_id: str
    store_id: str
    bill_no: str
    bill_date: str
    product_code: str
    batch: Optional[str] = None
    dont_consider_in_order: bool
