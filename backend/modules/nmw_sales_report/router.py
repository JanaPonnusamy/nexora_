"""NMW Sales Report (Bill-wise) API.

Warehouse (NMW) -> store dispatch bills. A bill becomes visible once despatched
(sync.SaleInformation.IssuedDate set); a super admin approves the dispatch before
store devices display it. Store users are scoped server-side to their own store's
inbound bills; super admin / purchase-manager users view every destination store.
"""

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_user
from modules.nmw_sales_report import service
from modules.nmw_sales_report.schemas import (
    ApproveRequest,
    ApproveResult,
    NmwSalesBillItemList,
    NmwSalesBillList,
)

router = APIRouter(prefix="/api/nmw-sales-report", tags=["NMW Sales Report"])


@router.get("/bills", response_model=NmwSalesBillList)
def list_bills(
    tenant_id: str,
    store_id: str = "",
    status: str = "all",
    date_from: str = "",
    date_to: str = "",
    current_user: dict = Depends(get_current_user),
):
    return service.list_bills(current_user, tenant_id, store_id.strip() or None, status, date_from, date_to)


@router.get("/bills/{bill_no}/items", response_model=NmwSalesBillItemList)
def bill_items(
    bill_no: str,
    tenant_id: str,
    bill_date: str = "",
    current_user: dict = Depends(get_current_user),
):
    return service.get_bill_items(current_user, tenant_id, bill_no, bill_date)


@router.post("/bills/approve", response_model=ApproveResult)
def approve(req: ApproveRequest, current_user: dict = Depends(get_current_user)):
    return service.approve(current_user, req)


# --- Store customer-code administration (super admin) ----------------------
# Maps each store to its NMW customer code (dbo.stores.ho_cust_code), which the
# report joins against SaleInformation.CustomerCode to route bills store-wise.


@router.get("/store-cust-codes")
def list_store_cust_codes(tenant_id: str, current_user: dict = Depends(get_current_user)):
    return service.list_store_cust_codes(current_user, tenant_id)


@router.put("/store-cust-codes/{store_id}")
def set_store_cust_code(
    store_id: str,
    tenant_id: str,
    cust_code: str = "",
    current_user: dict = Depends(get_current_user),
):
    return service.set_store_cust_code(current_user, tenant_id, store_id, cust_code)


@router.post("/store-cust-codes/import-legacy")
def import_store_cust_codes(tenant_id: str, current_user: dict = Depends(get_current_user)):
    return service.import_cust_codes(current_user, tenant_id)
