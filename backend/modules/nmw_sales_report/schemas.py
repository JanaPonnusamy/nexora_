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
    purchase_status: str = "not_found"      # completed | pending | not_found | error
    purchase_entry_no: Optional[str] = None  # store's completing GRN number (only when completed)


class NmwSalesBillList(BaseModel):
    bills: List[NmwSalesBill] = []
    can_approve: bool = False
    scope: str = "store"                    # store | all
    purchase_status_error: Optional[str] = None  # set only if the batched purchase-status lookup itself failed


class NmwPendingProduct(BaseModel):
    product_code: str
    product_name: Optional[str] = None
    required_qty: float = 0
    received_qty: float = 0


class NmwPurchaseEntry(BaseModel):
    purchase_status: str = "not_found"      # completed | pending | not_found
    matched_products: int = 0
    total_products: int = 0
    entry_no: Optional[str] = None          # one or more GRN numbers (comma-separated), earliest first
    completing_grn: Optional[str] = None    # the single latest GRN (matches the list column)
    entry_date: Optional[str] = None        # earliest matching GRN date
    pending_products: List[NmwPendingProduct] = []  # items not yet received (why a bill is still Pending)
    match_basis: Optional[str] = None       # bill_number | product_qty | none -- how completion was decided
    grn_amount: Optional[float] = None      # store's received value for the matched GRN (bill_number basis only)
    dest_store_id: Optional[str] = None
    dest_store_code: Optional[str] = None
    dest_store_name: Optional[str] = None
    reason: Optional[str] = None            # set when not_found because the lookup itself couldn't run


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
    packing: Optional[str] = None
    sublocation: Optional[str] = None


class NmwSalesBillSummary(BaseModel):
    """Reconciliation footer for a bill: the line-item sub-total plus the GST and
    round-off carried on the header, which together equal the header BillAmount.
    (subtotal = sum of line amounts = GrossAmount; cgst = sgst = header CGSTAmount
    for intra-state bills; roundoff absorbs any residual so total == bill_amount.)"""
    subtotal: float = 0
    cgst: float = 0
    sgst: float = 0
    tax_total: float = 0
    roundoff: float = 0
    bill_amount: float = 0
    is_transfer: int = 0


class NmwSalesBillItemList(BaseModel):
    items: List[NmwSalesBillItem] = []
    summary: Optional[NmwSalesBillSummary] = None


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
