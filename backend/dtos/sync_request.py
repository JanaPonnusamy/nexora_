
from __future__ import annotations

from pydantic import BaseModel

class SyncTableRequest(BaseModel):
    table_name: str
    sync_mode: str
    watermark_column: str | None = None
    window_days: int | None = None
    custom_where: str | None = None
    sync_order: int = 0
    is_active: bool = True

class SyncTableStatusRequest(BaseModel):
    is_active: bool

class ColumnMappingRequest(BaseModel):
    sync_table_id: str
    table_name: str
    column_name: str
    data_type: str
    is_selected: bool = False
    is_pk: bool = False
    is_hash: bool = False
    is_watermark: bool = False
    column_order: int = 0


class ScheduleRequest(BaseModel):
    schedule_name: str
    schedule_type: str = "DAILY"          # DAILY | ONCE
    store_id: str | None = None           # None = all stores in the tenant
    start_time: str                       # ISO datetime; DAILY uses time-of-day
    sync_mode: str = "FULL"
    is_enabled: bool = True
    tenant_id: str | None = None


class ScheduleSuspendRequest(BaseModel):
    suspended_until: str | None = None    # ISO datetime; null clears suspension


class ScheduleStatusRequest(BaseModel):
    is_enabled: bool
