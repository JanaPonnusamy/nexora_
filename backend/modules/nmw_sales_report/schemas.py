from typing import List, Optional

from pydantic import BaseModel


class NmwSalesBill(BaseModel):
    bill_no: Optional[str] = None          # BNumber (human-facing bill number)
    bill_number: Optional[int] = None      # BillNumber (numeric)
    bill_date: Optional[str] = None
    bill_time: Optional[str] = None
    issued_date: Optional[str] = None
    bill_amount: float = 0
    total_items: Optional[int] = None
    total_qty: float = 0
    customer_code: Optional[str] = None
    customer_name: Optional[str] = None
    is_transfer: int = 0
    bill_type: str = "Sale"                  # Sale | Transfer (TO stock-transfer)
    is_cancelled: int = 0
    dest_store_id: Optional[str] = None
    dest_store_code: Optional[str] = None
    dest_store_name: Optional[str] = None
    status: str = "pending"                 # pending | approved
    is_shown: int = 0                       # 1 once approved (visible to stores)
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


class NmwSalesBillList(BaseModel):
    bills: List[NmwSalesBill] = []
    can_approve: bool = False
    scope: str = "store"                    # store | all


class NmwSalesBillItem(BaseModel):
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    batch_no: Optional[str] = None
    expiry_date: Optional[str] = None
    qty: float = 0
    free_qty: float = 0
    mrp: float = 0
    rate: float = 0
    discount_percentage: float = 0
    amount: float = 0


class NmwSalesBillItemList(BaseModel):
    items: List[NmwSalesBillItem] = []


class BillKey(BaseModel):
    bill_date: str
    bill_no: str                            # BNumber


class ApproveRequest(BaseModel):
    tenant_id: str
    bills: List[BillKey] = []
    status: str = "approved"                # approved | pending (allows un-approve)
    remarks: Optional[str] = None


class ApproveResult(BaseModel):
    approved: int = 0
    status: str = "approved"
