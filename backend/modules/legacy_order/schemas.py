from typing import List, Optional

from pydantic import BaseModel


class SyncRequest(BaseModel):
    store_name: str
    tables: Optional[List[str]] = None  # None = the full legacy table plan


class OrderProcessRequest(BaseModel):
    store_name: str
    min_days: Optional[int] = None  # legacy defaults: 15 / 20
    max_days: Optional[int] = None
    mode: str = "local"  # 'local' = OrderNMC's synced copy, 'remote' = branch DB


class JobStarted(BaseModel):
    job_id: str
