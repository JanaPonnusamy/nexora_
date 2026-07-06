"""Stock Availability API — read-only stock lookup across a tenant's branches.

View-only module: no insert/update/delete endpoints. All data is sourced from
NEXORA_PLATFORM (synced `sync.*` tables) via stock.usp_* stored procedures.
"""

from typing import Optional

from fastapi import APIRouter

from modules.stock_availability import service
from modules.stock_availability.schemas import SearchResult

router = APIRouter(prefix="/api/stock-availability", tags=["Stock Availability"])


# ----- Search ----------------------------------------------------------------

@router.get("/products/search", response_model=SearchResult)
def search_products(tenant_id: str, q: str = "", only_stock: int = 0):
    """Tab 1 — partial, case-insensitive product-name search across branches."""
    return service.search_products(tenant_id, q, only_stock)


@router.get("/batches/search", response_model=SearchResult)
def search_batches(
    tenant_id: str,
    batch: str = "",
    mrp: str = "",
    product: str = "",
):
    """Tab 2 — search by batch number, MRP and/or product name across branches."""
    return service.search_batches(tenant_id, batch, mrp, product)


# ----- Detail panels (active product context) --------------------------------

@router.get("/products/details")
def product_details(tenant_id: str, store_id: str, product: str):
    return service.product_details(tenant_id, store_id, product)


@router.get("/products/batches")
def batch_details(tenant_id: str, store_id: str, product: str):
    return service.batch_details(tenant_id, store_id, product)


@router.get("/products/purchases")
def purchase_history(tenant_id: str, store_id: str, product: str):
    return service.purchase_history(tenant_id, store_id, product)


@router.get("/products/sales")
def sales_history(tenant_id: str, store_id: str, product: str):
    return service.sales_history(tenant_id, store_id, product)


@router.get("/products/bill")
def bill_items(
    tenant_id: str,
    store_id: str,
    bill_no: str,
    bill_date: Optional[str] = None,
):
    return service.bill_items(tenant_id, store_id, bill_no, bill_date)


@router.get("/products/movement")
def monthly_movement(tenant_id: str, store_id: str, product: str, months: int = 4):
    """Last N months (default 4) of PUR / SAL / TIN / TOUT / ADJ / STK totals."""
    return service.monthly_movement(tenant_id, store_id, product, months)


# ----- Bill Drawer (Purchase Manager detail panel) ---------------------------

@router.get("/bills/purchase")
def purchase_bill(
    tenant_id: str,
    store_id: str,
    grn_no: int,
    grn_date: Optional[str] = None,
):
    """All lines of one GRN (Purchase Bill Drawer). Header on every row."""
    return service.purchase_bill(tenant_id, store_id, grn_no, grn_date)


@router.get("/bills/sale")
def sales_bill(
    tenant_id: str,
    store_id: str,
    bill_no: str,
    bill_date: Optional[str] = None,
):
    """All lines of one sale bill (Sales Bill Drawer). Header on every row."""
    return service.sales_bill(tenant_id, store_id, bill_no, bill_date)


@router.get("/products/availability")
def product_availability(tenant_id: str, store_id: str, product: str):
    """Per-store stock + on-order qty for a product (drawer Availability tab)."""
    return service.product_availability(tenant_id, store_id, product)


@router.get("/customers/history")
def customer_history(tenant_id: str, store_id: str, customer_code: str):
    """A customer's last 10 bills (drawer Customer History tab)."""
    return service.customer_history(tenant_id, store_id, customer_code)


@router.get("/products/repeat")
def repeat_purchase(tenant_id: str, store_id: str, product: str):
    """Products usually bought together (drawer Repeat Purchase tab)."""
    return service.repeat_purchase(tenant_id, store_id, product)
