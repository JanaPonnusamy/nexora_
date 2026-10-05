from typing import List, Optional

from pydantic import BaseModel


class SyncRequest(BaseModel):
    store_name: str
    tables: Optional[List[str]] = None  # None = the full legacy table plan


class OrderProcessRequest(BaseModel):
    store_name: str
    min_days: Optional[int] = None  # Nexora defaults: 13 / 18
    max_days: Optional[int] = None
    mode: str = "local"  # 'local' = OrderNMC's synced copy, 'remote' = branch DB


class StockUpdateRequest(BaseModel):
    store_name: str
    source_store_name: str = "NMW"


class JobStarted(BaseModel):
    job_id: str


class ComparePreviousOrderRequest(BaseModel):
    store_name: str
    order_id: int


class CompareSupplierRequest(ComparePreviousOrderRequest):
    supplier_code: str


class UpdateOrderQtyRequest(BaseModel):
    order_qty: int


class UpdateQtyCheckRequest(BaseModel):
    order_qty: int


class WorkflowActionRequest(BaseModel):
    note: Optional[str] = None


class AssignSupplierRequest(BaseModel):
    supplier_code: str
    supplier_name: str


class ExportOrderRequest(BaseModel):
    supplier_code: str
    supplier_name: str
    mode: str = "history"  # matches the By-Supplier view's History/Live Stock toggle
    split_size: int = 0  # 0 = single file; >0 splits into "Part N of M" chunks (zipped)


class EmergencyRepairRequest(BaseModel):
    # Guard rail: the destructive REPAIR_ALLOW_DATA_LOSS path only runs when the
    # caller explicitly opts in. The UI sends this from a confirmation dialog.
    confirm: bool = False
