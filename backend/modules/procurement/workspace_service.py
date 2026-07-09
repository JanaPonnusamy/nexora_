"""Purchase Manager Workspace service (Sprint 2, Modules 1-3).

Orchestration + validation over workspace_repository. The PM may edit only
Final Quantity, Skip and Skip Reason (Module 1). Skipped items are retained
(Module 3). Business rules are enforced here in Python.
"""

import logging

from fastapi import HTTPException

from modules.procurement import workspace_repository as repo

logger = logging.getLogger("procurement.workspace")


def _require_item(tenant_id, order_item_id):
    item = repo.get_item(tenant_id, order_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Working item not found")
    return item


def list_workspace(tenant_id, refresh_id, filters, sort_by, sort_dir, page, page_size):
    items, total = repo.list_items(
        tenant_id, refresh_id, filters, sort_by, sort_dir, page, page_size
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_summary(tenant_id, refresh_id, filters):
    """Footer counts (Total / Pending Review / Assigned / Finalized / Skipped),
    computed in SQL over the whole refresh instead of reduced from every
    loaded row in the browser."""
    return repo.get_summary(tenant_id, refresh_id, filters)


def get_item(tenant_id, order_item_id):
    return _require_item(tenant_id, order_item_id)


# Business rules evaluated by the Decision Engine (PR-BR ids), for explainability.
_RULES_APPLIED = [
    "PR-BR-001 Rolling Sales Window", "PR-BR-002 Average Daily Sales",
    "PR-BR-003 Days Cover", "PR-BR-004 Min-Days Reorder Trigger",
    "PR-BR-005 Max-Days Target Stock", "PR-BR-006 Coverage Required",
    "PR-BR-007 Max-Day-Sale Floor", "PR-BR-008 Max-Bill Floor",
    "PR-BR-009 Final Required Quantity", "PR-BR-010 Movement Class",
    "PR-BR-011 Stock Status", "PR-BR-014 Effective Available",
    "PR-BR-015 Reason Code & Explainability", "PR-BR-016 Configurable Parameters",
]


def get_decision(tenant_id, order_item_id):
    decision = repo.get_decision(tenant_id, order_item_id)
    if not decision:
        raise HTTPException(status_code=404, detail="Working item not found")
    decision["business_rules_applied"] = _RULES_APPLIED
    return decision


def set_final_qty(tenant_id, order_item_id, final_qty, override_reason, reviewed_by):
    if final_qty is None or final_qty < 0:
        raise HTTPException(status_code=400, detail="final_qty cannot be negative")
    item = _require_item(tenant_id, order_item_id)
    # Cannot reduce below what's already assigned to suppliers.
    if final_qty < (item.get("assigned_qty") or 0):
        raise HTTPException(
            status_code=409,
            detail="final_qty cannot be below the already-assigned quantity",
        )
    repo.set_final_qty(tenant_id, order_item_id, final_qty, override_reason, reviewed_by)
    logger.info("Review final_qty tenant=%s item=%s qty=%s by=%s",
                tenant_id, order_item_id, final_qty, reviewed_by)
    return _require_item(tenant_id, order_item_id)


def restore_suggested(tenant_id, order_item_id, reviewed_by):
    item = _require_item(tenant_id, order_item_id)
    if (item.get("suggested_qty") or 0) < (item.get("assigned_qty") or 0):
        raise HTTPException(
            status_code=409,
            detail="Suggested quantity is below the already-assigned quantity",
        )
    repo.restore_suggested(tenant_id, order_item_id, reviewed_by)
    return _require_item(tenant_id, order_item_id)


def skip_item(tenant_id, order_item_id, skip_reason, reviewed_by):
    if not skip_reason or not skip_reason.strip():
        raise HTTPException(status_code=400, detail="skip_reason is required")
    item = _require_item(tenant_id, order_item_id)
    if (item.get("assigned_qty") or 0) > 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot skip an item that already has supplier assignments",
        )
    repo.skip_item(tenant_id, order_item_id, skip_reason, reviewed_by)
    logger.info("Review skip tenant=%s item=%s by=%s", tenant_id, order_item_id, reviewed_by)
    return _require_item(tenant_id, order_item_id)


def restore_item(tenant_id, order_item_id, reviewed_by):
    item = _require_item(tenant_id, order_item_id)
    if item.get("item_status") != "skipped":
        raise HTTPException(status_code=409, detail="Item is not skipped")
    repo.restore_item(tenant_id, order_item_id, reviewed_by)
    return _require_item(tenant_id, order_item_id)
