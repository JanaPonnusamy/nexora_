"""Stock Availability API — read-only stock lookup across a tenant's branches.

View-only module: no insert/update/delete endpoints. All data is sourced from
NEXORA_PLATFORM (synced `sync.*` tables) via stock.usp_* stored procedures.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_user
from modules.stock_availability import service
from modules.stock_availability.schemas import CoreBulkRequest, SalesOrderIgnoreUpdate, SearchResult

router = APIRouter(prefix="/api/stock-availability", tags=["Stock Availability"])


# ----- Search ----------------------------------------------------------------

@router.get("/products/search", response_model=SearchResult)
def search_products(tenant_id: str, q: str = "", only_stock: int = 0, current_user: dict = Depends(get_current_user)):
    """Tab 1 — partial, case-insensitive product-name search across branches."""
    return service.search_products(current_user, tenant_id, q, only_stock)


@router.get("/batches/search", response_model=SearchResult)
def search_batches(
    tenant_id: str,
    batch: str = "",
    mrp: str = "",
    product: str = "",
    current_user: dict = Depends(get_current_user),
):
    """Tab 2 — search by batch number, MRP and/or product name across branches."""
    return service.search_batches(current_user, tenant_id, batch, mrp, product)


# ----- Detail panels (active product context) --------------------------------

@router.get("/products/details")
def product_details(tenant_id: str, store_id: str, product: str, current_user: dict = Depends(get_current_user)):
    return service.product_details(current_user, tenant_id, store_id, product)


@router.get("/products/core")
def product_core(tenant_id: str, store_id: str, product: str, months: int = 3, current_user: dict = Depends(get_current_user)):
    """batches + purchases + sales + movement in one round trip (perf)."""
    return service.product_core(current_user, tenant_id, store_id, product, months)


@router.post("/products/core/bulk")
def product_core_bulk(payload: CoreBulkRequest, current_user: dict = Depends(get_current_user)):
    """Parallel per-store core loading in one HTTP request."""
    return service.product_core_bulk(current_user, payload.tenant_id, payload.items, payload.months)


@router.get("/products/batches")
def batch_details(tenant_id: str, store_id: str, product: str, current_user: dict = Depends(get_current_user)):
    return service.batch_details(current_user, tenant_id, store_id, product)


@router.get("/products/purchases")
def purchase_history(tenant_id: str, store_id: str, product: str, current_user: dict = Depends(get_current_user)):
    return service.purchase_history(current_user, tenant_id, store_id, product)


@router.get("/products/sales")
def sales_history(tenant_id: str, store_id: str, product: str, current_user: dict = Depends(get_current_user)):
    return service.sales_history(current_user, tenant_id, store_id, product)


@router.get("/products/bill")
def bill_items(
    tenant_id: str,
    store_id: str,
    bill_no: str,
    bill_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    return service.bill_items(current_user, tenant_id, store_id, bill_no, bill_date)


@router.get("/products/movement")
def monthly_movement(tenant_id: str, store_id: str, product: str, months: int = 4, current_user: dict = Depends(get_current_user)):
    """Last N months (default 4) of PUR / SAL / TIN / TOUT / ADJ / STK totals."""
    return service.monthly_movement(current_user, tenant_id, store_id, product, months)


# ----- Bill Drawer (Purchase Manager detail panel) ---------------------------

@router.get("/bills/purchase")
def purchase_bill(
    tenant_id: str,
    store_id: str,
    grn_no: int,
    grn_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """All lines of one GRN (Purchase Bill Drawer). Header on every row."""
    return service.purchase_bill(current_user, tenant_id, store_id, grn_no, grn_date)


@router.get("/bills/sale")
def sales_bill(
    tenant_id: str,
    store_id: str,
    bill_no: str,
    bill_date: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """All lines of one sale bill (Sales Bill Drawer). Header on every row."""
    return service.sales_bill(current_user, tenant_id, store_id, bill_no, bill_date)


@router.put("/bills/sale/ignore-order")
def set_sales_bill_line_ignore(payload: SalesOrderIgnoreUpdate, current_user: dict = Depends(get_current_user)):
    """Toggle ProductSaleInformation.DontConsiderInOrder for one bill line."""
    return service.set_sales_bill_line_ignore(
        current_user,
        payload.tenant_id,
        payload.store_id,
        payload.bill_no,
        payload.bill_date,
        payload.product_code,
        payload.batch,
        payload.dont_consider_in_order,
    )


@router.get("/products/availability")
def product_availability(tenant_id: str, store_id: str, product: str, current_user: dict = Depends(get_current_user)):
    """Per-store stock + on-order qty for a product (drawer Availability tab)."""
    return service.product_availability(current_user, tenant_id, store_id, product)


@router.get("/customers/history")
def customer_history(tenant_id: str, store_id: str, customer_code: str, current_user: dict = Depends(get_current_user)):
    """A customer's last 10 bills (drawer Customer History tab)."""
    return service.customer_history(current_user, tenant_id, store_id, customer_code)


@router.get("/products/repeat")
def repeat_purchase(tenant_id: str, store_id: str, product: str, current_user: dict = Depends(get_current_user)):
    """Products usually bought together (drawer Repeat Purchase tab)."""
    return service.repeat_purchase(current_user, tenant_id, store_id, product)
