"""Canonical procurement product identity.

A grid line is one product in one store. The code is the identity, not the
name: two codes with similar names stay separate, and the same code in two
stores stays separate. A repeated code inside one store is one line. Supplier
mappings and product-master copies may multiply that line in a join; they do
not create another product. The surviving row is kept as-is (quantity is never
summed), preferring the line that already carries an assignment or a quantity,
then the supplier mapping with stock.
"""

from __future__ import annotations


def canonical_product_code(value) -> str:
    """Store product code as text. Float '123.0' and int 123 are the same code."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        whole = text[:-2]
        if whole.lstrip("-").isdigit():
            return whole
    return text


def _first(row, names):
    for name in names:
        if name in row and row.get(name) is not None:
            return row.get(name)
    return None


def line_identity(row, extra_fields=()) -> tuple:
    """(store, product code). A row with no code stays its own line.

    extra_fields (for example the assigned supplier) stay part of the identity
    so two legitimate supplier assignments of one medicine are not merged.
    """
    code = canonical_product_code(
        _first(row, ("product_code", "ProductCode", "productcode"))
    )
    store = _first(row, ("store_id", "store_name", "StoreName", "storename")) or ""
    extra = tuple(str(_first(row, (name,)) or "") for name in extra_fields)
    if not code:
        token = _first(row, ("order_item_id", "supplier_stock_id", "supplier_product_code"))
        return ("unkeyed", str(store), str(token if token is not None else id(row)), *extra)
    return ("product", str(store), code, *extra)


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def choose_line(rows: list) -> dict:
    """One of `rows` (same identity). Does not add their quantities together."""
    def rank(row):
        assigned = _num(row.get("assigned_qty"))
        final = _num(_first(row, ("final_qty", "OrderQty", "orderqty")))
        suggested = _num(row.get("suggested_qty"))
        stock = _num(_first(row, ("available_stock", "S_Stock", "Stock", "SupplierStock")))
        has_sku = 1 if _first(row, ("SupplierProductCode", "supplier_product_code")) else 0
        wanted = str(_first(row, ("WantedType", "wantedtype", "wanted")) or "")
        additional = 1 if wanted == "Additional Row" else 0
        return (0 if assigned > 0 else 1, -final, -suggested, -stock, -has_sku, additional)

    return min(rows, key=rank)


def collapse_lines(rows, extra_fields=()) -> list:
    """One row per line identity, in first-seen order."""
    grouped: dict = {}
    order = []
    for row in rows or []:
        key = line_identity(row, extra_fields)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(row)
    return [choose_line(grouped[key]) for key in order]


def collapse_generated_payload(rows, code_index, qty_index, wanted_index):
    """One generated order tuple per product code. Quantity is not summed."""
    best = {}
    order = []
    for row in rows or []:
        code = canonical_product_code(row[code_index])
        key = code or ("raw", id(row))
        if key not in best:
            best[key] = row
            order.append(key)
            continue
        best[key] = _prefer_generated(best[key], row, qty_index, wanted_index)
    return [best[key] for key in order]


def _prefer_generated(current, candidate, qty_index, wanted_index):
    def rank(row):
        wanted = str(row[wanted_index] or "")
        additional = 1 if wanted == "Additional Row" else 0
        return (additional, -_num(row[qty_index]))

    return current if rank(current) <= rank(candidate) else candidate
