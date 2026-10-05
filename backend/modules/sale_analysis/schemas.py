"""Response/request schemas for the Sale Analysis module."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ProductOption(BaseModel):
    product_code: str
    product_name: Optional[str] = None
    supplier_code: Optional[str] = None
    supplier_name: Optional[str] = None
    current_stock: Optional[float] = None
    mrp: Optional[float] = None


class SupplierOption(BaseModel):
    supplier_code: str
    supplier_name: Optional[str] = None


class GroupSummary(BaseModel):
    group_id: str
    group_name: str
    item_count: int
    updated_at: Optional[str] = None


class GroupDetail(GroupSummary):
    product_names: List[str] = []


class GroupSaveRequest(BaseModel):
    group_name: str
    product_names: List[str] = []


class ReportColumn(BaseModel):
    key: str
    label: str
    align: str = "left"
    format: Optional[str] = None  # money | int | date | None


class ReportGroup(BaseModel):
    group_id: Optional[str] = None
    group_name: str
    summary: Dict[str, Any]
    rows: List[Dict[str, Any]]


class SaleAnalysisResult(BaseModel):
    window_label: str
    from_date: str
    to_date: str
    window_days: int
    target_days: int
    columns: List[ReportColumn]
    groups: List[ReportGroup]
    grand_summary: Optional[Dict[str, Any]] = None
