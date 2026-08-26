"""Non-Moving Report service — shapes the batch rows into the uniform
``{columns, rows, summary}`` result the frontend renders with one grid and
exports to Excel generically. Read-only.
"""

from decimal import Decimal

from fastapi import HTTPException

from modules.nonmoving_report import repository as repo

_MONEY, _INT, _DATE = "money", "int", "date"

_COLUMNS = [
    ("SupplierName", "Supplier", "left", None),
    ("ProductCode", "Code", "left", None),
    ("ProductName", "Product", "left", None),
    ("Pack", "Pack", "left", None),
    ("Batch", "Batch", "left", None),
    ("Stock", "Stock", "right", _INT),
    ("ExpiryDate", "Expiry", "center", _DATE),
    ("ReceivedDate", "Last Received", "center", _DATE),
    ("LastSoldDate", "Last Sold", "center", _DATE),
    ("Days", "Days", "right", _INT),
    ("PurchasePrice", "Purchase", "right", _MONEY),
    ("SalePrice", "Sale Price", "right", _MONEY),
    ("MRP", "MRP", "right", _MONEY),
    ("CostValue", "Cost Value", "right", _MONEY),
    ("SaleValue", "Sale Value", "right", _MONEY),
    ("GrnNumber", "GRN", "left", None),
    ("InvoiceNumber", "Invoice", "left", None),
    ("Rack", "Rack", "left", None),
]

_TOTAL_COLS = ["Stock", "CostValue", "SaleValue"]

_BASIS = ("sold", "received")


def _sum(rows, key):
    total = Decimal(0)
    for r in rows:
        v = r.get(key)
        if v is not None:
            total += Decimal(str(v))
    return total


def data(tenant_id, store_id, basis, min_days, max_days, include_nil,
         supplier_code, supplier_mode):
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    basis = (basis or "sold").lower()
    if basis not in _BASIS:
        raise HTTPException(status_code=400, detail=f"bad basis '{basis}'")
    try:
        min_days = int(min_days or 0)
        max_days = int(max_days) if max_days not in (None, "") else None
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="min_days/max_days must be integers")

    rows = repo.data(tenant_id, store_id or None, basis, min_days, max_days,
                     bool(include_nil), supplier_code or None, int(supplier_mode or 0))

    columns = [{"key": k, "label": lbl, "align": al, "format": fmt}
               for (k, lbl, al, fmt) in _COLUMNS]

    summary = None
    if rows:
        summary = {"SupplierName": "Total", "Days": len(rows)}
        for col in _TOTAL_COLS:
            summary[col] = _sum(rows, col)

    return {
        "level": f"non-moving-{basis}",
        "basis": basis,
        "columns": columns,
        "rows": rows,
        "summary": summary,
    }


def suppliers(tenant_id, store_id, supplier_mode):
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    return {"rows": repo.suppliers(tenant_id, store_id or None, int(supplier_mode or 0))}
