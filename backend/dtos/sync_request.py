
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
