"""GRN reconciliation business rules (pure Python, no I/O) — Sprint 3.

Turns matched supplier receipts into per-assignment and per-item receipt state.
No SQL here; the repository supplies the numbers and persists the results.
"""

# per-assignment status
EXPORTED = "exported"            # ordered, nothing received yet
PARTIAL_RECEIVED = "partial_received"
RECEIVED = "received"

# per-order-item receipt state
ITEM_PENDING = "pending"
ITEM_PARTIAL = "partial"
ITEM_COMPLETED = "completed"


def assignment_state(assigned_qty, received_qty):
    """Return (remaining_qty, status) for one assignment after receipt.

    remaining is floored at 0 (over-receipt does not create negative pending).
    """
    assigned = assigned_qty or 0
    received = received_qty or 0
    remaining = max(0.0, assigned - received)
    if received <= 0:
        status = EXPORTED
    elif received >= assigned:
        status = RECEIVED
    else:
        status = PARTIAL_RECEIVED
    return remaining, status


def item_receipt_state(final_qty, received_qty):
    """Return (remaining_qty = pending, item_status) for an order item.

    Pending = Final − Received (floored at 0). This is the value that feeds the
    next Refresh (PR-BR remaining/pending).
    """
    final = final_qty or 0
    received = received_qty or 0
    remaining = max(0.0, final - received)
    if received <= 0:
        status = ITEM_PENDING
    elif received >= final:
        status = ITEM_COMPLETED
    else:
        status = ITEM_PARTIAL
    return remaining, status


def match_receipts(assignment, receipts):
    """Sum the receipts that match an assignment on product + supplier.

    `receipts` is a list of dicts (product_code, supplier_code, received_qty,
    grn_no, supplier_bill_no). Returns (received_qty, grn_no, supplier_bill_no).
    """
    total = 0.0
    grn_no = None
    bill_no = None
    for r in receipts:
        if r.get("product_code") != assignment.get("product_code"):
            continue
        # Supplier match when the receipt carries a supplier; otherwise match by
        # product alone (synced PurchaseTrans has no supplier column).
        r_supplier = r.get("supplier_code")
        if r_supplier is not None and r_supplier != assignment.get("supplier_code"):
            continue
        total += float(r.get("received_qty") or 0)
        grn_no = r.get("grn_no") or grn_no
        bill_no = r.get("supplier_bill_no") or bill_no
    return total, grn_no, bill_no
