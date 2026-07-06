"""Response schemas for the Reports module."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ReportColumn(BaseModel):
    key: str
    label: str
    align: str = "left"          # left | right | center
    format: Optional[str] = None  # money | int | date | None


class ReportDef(BaseModel):
    key: str
    label: str
    group: str
    needs_date_range: bool = False
    needs_dwell_days: bool = False
    needs_supplier: bool = False
    needs_division: bool = False


class ReportResult(BaseModel):
    report: str
    title: str
    columns: List[ReportColumn]
    rows: List[Dict[str, Any]]
    summary: Optional[Dict[str, Any]] = None


class SupplierOption(BaseModel):
    supplier_code: str
    supplier_name: Optional[str] = None
