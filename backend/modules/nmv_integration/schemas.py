"""Request/response models for the NMV integration API.

Kept deliberately small and explicit: the boundary never accepts a free-form
StoreName (the store is taken from the authenticated device + the validated
path), and the order-result path accepts only the seven whitelisted columns.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# The only OrderManagement columns the NMV side may write back (see CONTRACT A.2).
ORDER_RESULT_COLUMNS = (
    "OrderQty", "OrQty", "QtyCheck", "Remarks", "OrSupplier", "OrSupplierCode", "Status",
)


# ---- downlink / read responses -------------------------------------------

class ConfigResponse(BaseModel):
    store_code: str
    config_version: int
    poll_interval_seconds: int
    max_rows_per_page: int
    server_time: str


class TableWatermark(BaseModel):
    entity: str
    strategy: str
    watermark: int | str | None = None


class ManifestResponse(BaseModel):
    store_code: str
    store_name: str
    config_version: int
    current_order_id: int | None = None
    uplink: list[TableWatermark]
    downlink: list[TableWatermark]
    server_time: str


class ChangesResponse(BaseModel):
    entity: str
    rows: list[dict[str, Any]]
    next_cursor: str | None = None
    watermark: int | str | None = None
    has_more: bool = False


class OrdersResponse(BaseModel):
    store_code: str
    order_id: int | None = None
    rows: list[dict[str, Any]]


class StatusResponse(BaseModel):
    store_code: str
    store_name: str
    watermarks: list[TableWatermark]
    recent: list[dict[str, Any]]


# ---- uplink / write requests ---------------------------------------------

class UplinkRequest(BaseModel):
    """One batch of NMV POS rows for a single source table."""

    message_id: str = Field(..., description="Client-generated UUID; idempotency key")
    table: str = Field(..., min_length=1, max_length=100)
    columns: list[str] = Field(..., min_length=1)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    # The high-water value this batch advances the uplink watermark to, once
    # merged (e.g. the max ID in the batch). Interpreted per the table strategy.
    watermark: int | str | None = None
    # True only for the FIRST page of a full-snapshot table (e.g. Batches), so
    # HO zeroes the prior snapshot before merging. Never set on incremental tables.
    snapshot_reset: bool = False


class UplinkResponse(BaseModel):
    message_id: str
    table: str
    rows_in: int
    rows_applied: int
    skipped_duplicate: bool = False
    errors: list[str] = Field(default_factory=list)
    watermark: int | str | None = None


class OrderResultItem(BaseModel):
    product_code: Any
    order_qty: float | None = None
    or_qty: float | None = None
    qty_check: int | None = None
    remarks: str | None = None
    or_supplier: str | None = None
    or_supplier_code: str | None = None
    status: int | None = None
    # Optimistic guard: if given, the update only applies when the current row
    # Status still matches (avoids clobbering a concurrent HO-side change).
    expected_status: int | None = None


class OrderResultsRequest(BaseModel):
    message_id: str = Field(..., description="Client-generated UUID; idempotency key")
    order_id: int
    results: list[OrderResultItem] = Field(default_factory=list)


class OrderResultsResponse(BaseModel):
    message_id: str
    order_id: int
    rows_in: int
    rows_applied: int
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    skipped_duplicate: bool = False


class AckRequest(BaseModel):
    entity: str = Field(..., min_length=1, max_length=100)
    watermark: int | str | None = None


class AckResponse(BaseModel):
    entity: str
    watermark: int | str | None = None
