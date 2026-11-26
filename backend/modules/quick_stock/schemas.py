from __future__ import annotations

from pydantic import BaseModel


class CrossStoreMatchRequest(BaseModel):
    tenant_id: str
    source_store_id: str
    source_product_code: str
    source_product_name: str
    target_store_ids: list[str]


class CoreBulkItem(BaseModel):
    store_id: str
    product_code: str


class CoreBulkRequest(BaseModel):
    tenant_id: str
    months: int = 3
    items: list[CoreBulkItem] = []


class CoreBulkSplitRequest(BaseModel):
    """Sales/Purchase toggle: `mode` picks which transaction type is fetched
    for every store in `items` -- the other type is never queried."""
    tenant_id: str
    months: int = 4
    mode: str = "sales"  # "sales" | "purchase"
    items: list[CoreBulkItem] = []
