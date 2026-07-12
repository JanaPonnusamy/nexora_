"""Request/response shapes for the Pass Gen module."""

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from modules.pass_gen.passcode import MAX_BASE36_2


class PassGenStore(BaseModel):
    store_id: str
    tenant_id: str
    store_code: str
    store_name: Optional[str] = None
    numeric_code: Optional[int] = None


class StoreCodeInput(BaseModel):
    """None clears the mapping. 0..99 keeps the code's 2-digit store field."""
    numeric_code: Optional[int] = Field(default=None, ge=0, le=99)


class GenerateRow(BaseModel):
    """One day-range row. Empty store_ids means every mapped store."""
    row_id: str
    store_ids: List[str] = []
    min_days: int = Field(ge=0, le=MAX_BASE36_2)
    max_days: int = Field(ge=0, le=MAX_BASE36_2)
    order_yes: int = Field(default=0, ge=0, le=1)
    compare_last_order: int = Field(default=0, ge=0, le=1)


class GenerateRequest(BaseModel):
    """Order No and target date are shared by every row of one generation."""
    order_no: int = Field(ge=0, le=9)
    target_date: date
    rows: List[GenerateRow]


class PassGenResult(BaseModel):
    store_id: str
    store_code: str
    store_name: Optional[str] = None
    numeric_code: int
    passcode: str


class GenerateRowResult(BaseModel):
    row_id: str
    results: List[PassGenResult] = []
    skipped: List[str] = []


class GenerateResponse(BaseModel):
    rows: List[GenerateRowResult] = []
