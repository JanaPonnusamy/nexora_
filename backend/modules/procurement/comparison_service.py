"""Next-Refresh comparison service (Sprint 3, Module 4).

carry_forward seeds the previous Refresh's carried pending into a freshly
created Refresh so pending automatically influences the next cycle. Products
already completely received (remaining <= 0) are never carried. Runs on a
caller-owned connection so it participates in the refresh-creation flow.
"""

from modules.procurement import comparison_repository as repo
from modules.procurement import refresh_comparison as rules


def carry_forward(conn, tenant_id, previous_refresh_id, refresh, created_by):
    """Insert carried pending from the previous Refresh into `refresh`.

    Returns the number of carried lines added. Idempotent per product: a product
    already present in the new Refresh is not duplicated.
    """
    if not previous_refresh_id:
        return 0

    carried = 0
    for row in repo.carried_pending(conn, tenant_id, previous_refresh_id):
        include, qty = rules.adjust_suggested(
            engine_suggested=0,
            previous_remaining=row["remaining_qty"],
            carried=True,
            previously_completed=False,
        )
        if not include:
            continue
        if repo.exists_in_refresh(conn, tenant_id, refresh["refresh_id"], row["product_code"]):
            continue
        repo.insert_carried(
            conn, tenant_id, refresh, row["product_code"],
            row.get("product_id"), qty, created_by,
        )
        carried += 1
    return carried
