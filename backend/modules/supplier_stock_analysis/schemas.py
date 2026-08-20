"""Contracts for Supplier Stock Analysis."""

from typing import Dict, Optional

from pydantic import BaseModel


class MappingUpdate(BaseModel):
    tenant_id: str
    store_id: str
    supplier_code: str
    supplier_product_code: str
    supplier_product_name: Optional[str] = None
    product_code: str
    username: Optional[str] = None


class ImportRequest(BaseModel):
    mapping: Dict[str, str]
