from typing import List, Optional

from pydantic import BaseModel


class StockIntegrityRow(BaseModel):
    store_code: Optional[str] = None
    store_name: Optional[str] = None
    store_id: Optional[str] = None
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    store_batch_total: float = 0
    nexora_total_stock: float = 0
    difference: float = 0


class StockIntegrityResult(BaseModel):
    rows: List[StockIntegrityRow] = []
    mismatch_count: int = 0


class SyncDriftRow(BaseModel):
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    live_batch_total: float = 0
    synced_batch_total: float = 0
    difference: float = 0


class SyncDriftResult(BaseModel):
    rows: List[SyncDriftRow] = []
    drift_count: int = 0
    live_product_count: int = 0
    synced_product_count: int = 0


class RepairResult(BaseModel):
    repaired: int = 0
    remaining_mismatches: int = 0
