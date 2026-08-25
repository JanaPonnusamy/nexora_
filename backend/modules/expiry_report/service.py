"""Expiry Report service — shapes each drill-down level into a uniform
``{columns, rows, summary}`` result (ordered columns with align/format meta +
an optional totals row) so the frontend renders each level with one grid and
exports each to Excel generically. Read-only.
"""

from decimal import Decimal

from fastapi import HTTPException

from modules.expiry_report import repository as repo

_MONEY, _INT, _DATE = "money", "int", "date"

# Per-level ordered column metadata: key -> (label, align, format).
_META = {
    "store-summary": [
        ("StoreName", "Store", "left", None),
        ("GivenQty", "Given Qty", "right", _INT),
        ("ReceivedQty", "Received Qty", "right", _INT),
        ("RejectQty", "Reject Qty", "right", _INT),
        ("PendingQty", "Pending Qty", "right", _INT),
        ("GivenValue", "Given Value", "right", _MONEY),
        ("ReceivedValue", "Received Value", "right", _MONEY),
        ("PendingValue", "Pending Value", "right", _MONEY),
    ],
    "supplier-summary": [
        ("SupplierName", "Supplier", "left", None),
        ("Acks", "Acks", "right", _INT),
        ("GivenQty", "Given Qty", "right", _INT),
        ("ReceivedQty", "Received Qty", "right", _INT),
        ("RejectQty", "Reject Qty", "right", _INT),
        ("PendingQty", "Pending Qty", "right", _INT),
        ("GivenValue", "Given Value", "right", _MONEY),
        ("ReceivedValue", "Received Value", "right", _MONEY),
        ("PendingValue", "Pending Value", "right", _MONEY),
    ],
    "pending-months": [
        ("Period", "Month", "left", None),
        ("Lines", "Lines", "right", _INT),
        ("PendingQty", "Pending Qty", "right", _INT),
        ("PendingValue", "Pending Value", "right", _MONEY),
    ],
    "pending-by-month": [
        ("SupplierName", "Supplier", "left", None),
        ("AckNumber", "Ack No", "left", None),
        ("AckDate", "Ack Date", "center", _DATE),
        ("ProductCode", "Code", "left", None),
        ("ProductName", "Product", "left", None),
        ("Batch", "Batch", "left", None),
        ("ExpiryDate", "Expiry", "center", _DATE),
        ("Qty", "Qty", "right", _INT),
        ("Free", "Free", "right", _INT),
        ("Rate", "Rate", "right", _MONEY),
        ("MRP", "MRP", "right", _MONEY),
        ("Value", "Value", "right", _MONEY),
        ("DaysPending", "Days", "right", _INT),
        ("Remarks", "Remarks", "left", None),
    ],
    "supplier-pending": [
        ("ProductCode", "Code", "left", None),
        ("ProductName", "Product", "left", None),
        ("Batch", "Batch", "left", None),
        ("ExpiryDate", "Expiry", "center", _DATE),
        ("AckNumber", "Ack No", "left", None),
        ("AckDate", "Ack Date", "center", _DATE),
        ("Qty", "Qty", "right", _INT),
        ("Free", "Free", "right", _INT),
        ("Rate", "Rate", "right", _MONEY),
        ("MRP", "MRP", "right", _MONEY),
        ("Value", "Value", "right", _MONEY),
        ("DaysPending", "Days", "right", _INT),
        ("Remarks", "Remarks", "left", None),
    ],
    "supplier-acks": [
        ("AckNumber", "Ack No", "left", None),
        ("AckDate", "Ack Date", "center", _DATE),
        ("GivenQty", "Given Qty", "right", _INT),
        ("ReceivedQty", "Received Qty", "right", _INT),
        ("RejectQty", "Reject Qty", "right", _INT),
        ("PendingQty", "Pending Qty", "right", _INT),
        ("GivenValue", "Given Value", "right", _MONEY),
        ("ReceivedValue", "Received Value", "right", _MONEY),
        ("PendingValue", "Pending Value", "right", _MONEY),
        ("Remarks", "Remarks", "left", None),
    ],
    "ack-products": [
        ("ProductCode", "Code", "left", None),
        ("ProductName", "Product", "left", None),
        ("Batch", "Batch", "left", None),
        ("ExpiryDate", "Expiry", "center", _DATE),
        ("GivenQty", "Given Qty", "right", _INT),
        ("Free", "Free", "right", _INT),
        ("ReceivedQty", "Received Qty", "right", _INT),
        ("RejectQty", "Reject Qty", "right", _INT),
        ("Rate", "Rate", "right", _MONEY),
        ("MRP", "MRP", "right", _MONEY),
        ("Value", "Value", "right", _MONEY),
        ("Remarks", "Remarks", "left", None),
    ],
}

# Which numeric columns get a totals row per level; first text col holds "Total".
_TOTALS = {
    "store-summary": ("StoreName", ["GivenQty", "ReceivedQty", "RejectQty",
                                    "PendingQty", "GivenValue", "ReceivedValue",
                                    "PendingValue"]),
    "supplier-summary": ("SupplierName", ["Acks", "GivenQty", "ReceivedQty",
                                          "RejectQty", "PendingQty", "GivenValue",
                                          "ReceivedValue", "PendingValue"]),
    "pending-months": ("Period", ["Lines", "PendingQty", "PendingValue"]),
    "pending-by-month": ("ProductName", ["Qty", "Free", "Value"]),
    "supplier-pending": ("ProductName", ["Qty", "Free", "Value"]),
    "supplier-acks": ("AckNumber", ["GivenQty", "ReceivedQty", "RejectQty",
                                    "PendingQty", "GivenValue", "ReceivedValue",
                                    "PendingValue"]),
    "ack-products": ("ProductName", ["GivenQty", "Free", "ReceivedQty",
                                     "RejectQty", "Value"]),
}

_FN = {
    "store-summary": lambda t, s, sup, ack, mon: repo.store_summary(t),
    "supplier-summary": lambda t, s, sup, ack, mon: repo.supplier_summary(t, s),
    "supplier-pending": lambda t, s, sup, ack, mon: repo.supplier_pending(t, s, sup),
    "supplier-acks": lambda t, s, sup, ack, mon: repo.supplier_acks(t, s, sup),
    "ack-products": lambda t, s, sup, ack, mon: repo.ack_products(t, s, ack),
    "pending-months": lambda t, s, sup, ack, mon: repo.pending_months(t, s),
    "pending-by-month": lambda t, s, sup, ack, mon: repo.pending_by_month(t, s, mon),
}


def _columns(level):
    return [{"key": k, "label": lbl, "align": al, "format": fmt}
            for (k, lbl, al, fmt) in _META[level]]


def _sum(rows, key):
    total = Decimal(0)
    for r in rows:
        v = r.get(key)
        if v is not None:
            total += Decimal(str(v))
    return total


def _summary(level, rows):
    if not rows:
        return None
    label_col, num_cols = _TOTALS[level]
    out = {label_col: "Total"}
    for col in num_cols:
        out[col] = _sum(rows, col)
    return out


_GROUP_LABEL = {"summary": "Store", "ack": "Ack No", "month": "Month",
                "supplier": "Supplier", "product": "Product"}

_STATUS_MEASURES = {
    "all": [("GivenQty", "Given Qty", _INT), ("ReceivedQty", "Received Qty", _INT),
            ("RejectQty", "Reject Qty", _INT), ("PendingQty", "Pending Qty", _INT),
            ("GivenValue", "Given Value", _MONEY), ("ReceivedValue", "Received Value", _MONEY),
            ("PendingValue", "Pending Value", _MONEY)],
    "received": [("ReceivedQty", "Received Qty", _INT), ("ReceivedValue", "Received Value", _MONEY)],
    "pending": [("PendingQty", "Pending Qty", _INT), ("PendingValue", "Pending Value", _MONEY)],
    "rejected": [("RejectQty", "Reject Qty", _INT), ("RejectValue", "Reject Value", _MONEY)],
}


def date_bounds(tenant_id, store_id=None):
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    return repo.date_bounds(tenant_id, store_id or None)


def expiry_data(tenant_id, store_id, from_date, to_date, status, group_by):
    status = (status or "all").lower()
    group_by = (group_by or "summary").lower()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    if status not in _STATUS_MEASURES:
        raise HTTPException(status_code=400, detail=f"bad status '{status}'")
    if group_by not in _GROUP_LABEL:
        raise HTTPException(status_code=400, detail=f"bad group_by '{group_by}'")
    if not (from_date and to_date):
        raise HTTPException(status_code=400, detail="from and to dates are required")

    rows = repo.expiry_data(tenant_id, store_id or None, from_date, to_date, status, group_by)

    columns = [{"key": "Group", "label": _GROUP_LABEL[group_by], "align": "left", "format": None}]
    if group_by == "ack":
        columns.append({"key": "AckDate", "label": "Ack Date", "align": "center", "format": _DATE})
        columns.append({"key": "Supplier", "label": "Supplier", "align": "left", "format": None})
    for key, label, fmt in _STATUS_MEASURES[status]:
        columns.append({"key": key, "label": label, "align": "right", "format": fmt})

    summary = None
    if rows:
        summary = {"Group": "Total"}
        for key, _, _ in _STATUS_MEASURES[status]:
            summary[key] = _sum(rows, key)

    return {
        "level": f"data-{status}-{group_by}",
        "status": status,
        "group_by": group_by,
        "columns": columns,
        "rows": rows,
        "summary": summary,
    }


def run(level, tenant_id, store_id=None, supplier_code=None, ack_number=None,
        month=None):
    if level not in _FN:
        raise HTTPException(status_code=404, detail=f"Unknown level '{level}'")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    if level in ("supplier-summary", "supplier-pending", "supplier-acks",
                 "ack-products", "pending-months", "pending-by-month") and not store_id:
        raise HTTPException(status_code=400, detail="store_id is required")
    if level in ("supplier-pending", "supplier-acks") and not supplier_code:
        raise HTTPException(status_code=400, detail="supplier_code is required")
    if level == "ack-products" and not ack_number:
        raise HTTPException(status_code=400, detail="ack_number is required")
    if level == "pending-by-month" and not month:
        raise HTTPException(status_code=400, detail="month is required")

    _, rows = _FN[level](tenant_id, store_id, supplier_code, ack_number, month)
    return {
        "level": level,
        "columns": _columns(level),
        "rows": rows,
        "summary": _summary(level, rows),
    }
