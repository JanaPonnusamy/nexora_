"""Expiry Stock (Cutting Expiry) service — shapes the batch listing into the
uniform ``{columns, rows, summary}`` result the frontend grid + Excel export
already consume. Read-only.

Cost / PTR / Tax / Supplier are returned as ``optional`` columns so the UI can
default-hide them and let the user add them from the column settings.
"""

from decimal import Decimal

from fastapi import HTTPException

from modules.expiry_stock import repository as repo

_MONEY, _INT, _QTY, _DATE, _MARK = "money", "int", "qty", "date", "mark"

# key, label, align, format, optional(default-hidden)
_COLUMNS = [
    ("ProductCode", "Code", "left", None, False),
    ("ProductName", "Product", "left", None, False),
    ("UnitDescription", "Unit", "left", None, False),
    ("Loc", "Loc", "left", None, False),
    ("TotalStock", "Total Stock", "right", _QTY, False),
    ("BatchStock", "Batch Stock", "right", _QTY, False),
    ("Batch", "Batch", "left", None, False),
    ("ExpiryDate", "Expiry", "center", _DATE, False),
    ("MRP", "MRP", "right", _MONEY, False),
    ("DaysExpired", "Days Expired", "right", _INT, False),
    ("Cutting", "Cutting", "center", _MARK, False),
    ("Cost", "Cost", "right", _MONEY, True),
    ("PTR", "PTR", "right", _MONEY, True),
    ("Tax", "Tax", "left", None, True),
    ("Supplier", "Supplier", "left", None, True),
]


def _columns():
    return [{"key": k, "label": lbl, "align": al, "format": fmt, "optional": opt}
            for (k, lbl, al, fmt, opt) in _COLUMNS]


def _sum(rows, key):
    total = Decimal(0)
    for r in rows:
        v = r.get(key)
        if v is not None:
            total += Decimal(str(v))
    return total


def date_bounds(tenant_id, store_id):
    if not (tenant_id and store_id):
        raise HTTPException(status_code=400, detail="tenant_id and store_id are required")
    return repo.date_bounds(tenant_id, store_id)


def suppliers(tenant_id, store_id):
    if not (tenant_id and store_id):
        raise HTTPException(status_code=400, detail="tenant_id and store_id are required")
    _, rows = repo.suppliers(tenant_id, store_id)
    return {"suppliers": rows}


def report(tenant_id, store_id, supplier_code=None, exp_from=None, exp_to=None,
           only_cutting=False):
    if not (tenant_id and store_id):
        raise HTTPException(status_code=400, detail="tenant_id and store_id are required")

    _, rows = repo.report(tenant_id, store_id, supplier_code or None,
                          exp_from or None, exp_to or None, bool(only_cutting))

    # Cutting mark rendered as text; keep the raw flag for row styling.
    for r in rows:
        r["_cutting"] = bool(r.get("Cutting"))
        r["Cutting"] = "Cutting" if r.get("Cutting") else ""

    summary = None
    if rows:
        summary = {
            "ProductName": f"Total ({len(rows)} batches)",
            "BatchStock": _sum(rows, "BatchStock"),
        }

    return {
        "level": "expiry-stock",
        "columns": _columns(),
        "rows": rows,
        "summary": summary,
    }
