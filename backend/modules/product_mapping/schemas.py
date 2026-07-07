"""Pydantic request schemas for the Product Mapping API."""

from typing import List, Optional

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    source_store_id: str = Field(..., min_length=1)
    target_store_id: str = Field(..., min_length=1)
    actor: Optional[str] = None


class ApproveRequest(BaseModel):
    # optional target => choose a specific candidate (re-map + approve)
    target_product_code: Optional[str] = Field(None, max_length=50)
    target_product_name: Optional[str] = Field(None, max_length=400)
    actor: Optional[str] = None


class RejectRequest(BaseModel):
    actor: Optional[str] = None


class BulkReviewItem(BaseModel):
    mapping_id: str = Field(..., min_length=1)
    # present => manual override (re-map to this target before approving)
    target_product_code: Optional[str] = Field(None, max_length=50)
    target_product_name: Optional[str] = Field(None, max_length=400)


class BulkReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(APPROVE|REJECT)$")
    items: List[BulkReviewItem] = Field(..., min_length=1)
    source_store_id: str = Field(..., min_length=1)
    target_store_id: str = Field(..., min_length=1)
    page: int = Field(1, ge=1)
    page_size: int = Field(50, ge=1, le=200)
    actor: Optional[str] = None


class DictionaryTermCreate(BaseModel):
    term: str = Field(..., min_length=1, max_length=50)
    canonical: Optional[str] = Field(None, max_length=50)
    kind: str = Field("DOSAGE_FORM", max_length=20)
    actor: Optional[str] = None


class DictionaryTermUpdate(BaseModel):
    term: Optional[str] = Field(None, max_length=50)
    canonical: Optional[str] = Field(None, max_length=50)
    kind: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None
    actor: Optional[str] = None
