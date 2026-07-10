"""Supplier Assignment service (Sprint 2, Modules 5 & 7).

Single / bulk assignment, supplier change and removal, with the Module 7
validations enforced in Python:
  * one product may carry at most ONE active supplier assignment per cycle —
    the backend is the final authority here, never just the frontend
  * assigned qty may not exceed the item's Final Quantity
  * quantity must be > 0 (no zero / negative)
Reassigning to a different supplier is a change_supplier call, never a second
assign_single insert — assign_single/assign_bulk reject a product that
already has a live assignment to a different supplier (409 / per-item skip).
Order-item totals are recomputed from the live assignments after every change.
"""

from fastapi import HTTPException

from config.database import get_connection
from modules.procurement import assignment_repository as repo
from modules.procurement import workspace_repository as items_repo

import logging

logger = logging.getLogger("procurement.assignment")


def _require_item(tenant_id, order_item_id):
    item = items_repo.get_item(tenant_id, order_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Working item not found")
    return item


def _require_assignment(tenant_id, assignment_id):
    a = repo.get_assignment(tenant_id, assignment_id)
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return a


def _validate_qty(qty):
    if qty is None or qty <= 0:
        raise HTTPException(status_code=400, detail="assigned_qty must be > 0")


def _validate_supplier(supplier_code):
    if not supplier_code or not str(supplier_code).strip():
        raise HTTPException(status_code=400, detail="supplier_code is required")


def list_for_item(tenant_id, order_item_id):
    _require_item(tenant_id, order_item_id)
    return {"items": repo.list_by_order_item(tenant_id, order_item_id)}


def list_for_refresh(tenant_id, refresh_id):
    """Every live assignment for a Refresh, one query — the Supplier Queue reads
    this instead of fanning out one /assignments call per assigned item."""
    return {"items": repo.list_by_refresh(tenant_id, refresh_id)}


def assign_single(tenant_id, order_item_id, supplier_code, qty, remarks, created_by):
    _validate_supplier(supplier_code)
    _validate_qty(qty)
    item = _require_item(tenant_id, order_item_id)
    if item.get("item_status") == "skipped":
        raise HTTPException(status_code=409, detail="Item is skipped")

    conn = get_connection()
    try:
        if repo.duplicate_active_exists(conn, tenant_id, order_item_id, supplier_code):
            raise HTTPException(
                status_code=409,
                detail="An active assignment for this supplier already exists",
            )
        existing = repo.any_active_assignment(conn, tenant_id, order_item_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Product already assigned to a different supplier",
                    "assignment_id": existing["assignment_id"],
                    "supplier_code": existing["supplier_code"],
                },
            )
        already = repo.active_assigned_total(conn, tenant_id, order_item_id)
        if already + qty > (item["final_qty"] or 0):
            raise HTTPException(
                status_code=409,
                detail="Assigned quantity would exceed the item's final quantity",
            )
        assignment_id = repo.insert_assignment(
            conn, item, supplier_code, qty, remarks, created_by
        )
        repo.recompute_order_item(conn, tenant_id, order_item_id)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info("Assignment created tenant=%s item=%s supplier=%s qty=%s by=%s",
                tenant_id, order_item_id, supplier_code, qty, created_by)
    return {
        "assignment": _require_assignment(tenant_id, assignment_id),
        "item": _require_item(tenant_id, order_item_id),
    }


def assign_bulk(tenant_id, supplier_code, specs, created_by):
    """Assign one supplier to many items. specs: [{order_item_id, qty?}].

    Each item is validated independently; failures are reported (not fatal) so a
    single bad line doesn't abort the whole batch. qty defaults to remaining_qty.
    """
    _validate_supplier(supplier_code)
    results = []
    conn = get_connection()
    try:
        for spec in specs:
            oid = spec.get("order_item_id")
            try:
                item = items_repo.get_item(tenant_id, oid)
                if not item:
                    raise ValueError("item not found")
                if item.get("item_status") == "skipped":
                    raise ValueError("item is skipped")
                qty = spec.get("qty")
                if qty is None:
                    qty = item.get("remaining_qty") or 0
                if qty <= 0:
                    raise ValueError("no remaining quantity to assign")
                if repo.duplicate_active_exists(conn, tenant_id, oid, supplier_code):
                    raise ValueError("duplicate active assignment")
                existing = repo.any_active_assignment(conn, tenant_id, oid)
                if existing:
                    raise ValueError(
                        f"already assigned to a different supplier ({existing['supplier_code']})"
                    )
                already = repo.active_assigned_total(conn, tenant_id, oid)
                if already + qty > (item["final_qty"] or 0):
                    raise ValueError("would exceed final quantity")
                repo.insert_assignment(
                    conn, item, supplier_code, qty, spec.get("remarks"), created_by
                )
                repo.recompute_order_item(conn, tenant_id, oid)
                results.append({"order_item_id": oid, "status": "assigned", "qty": qty})
            except ValueError as exc:
                results.append(
                    {"order_item_id": oid, "status": "skipped", "reason": str(exc)}
                )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    assigned = sum(1 for r in results if r["status"] == "assigned")
    logger.info("Bulk assignment tenant=%s supplier=%s assigned=%s skipped=%s by=%s",
                tenant_id, supplier_code, assigned, len(results) - assigned, created_by)
    return {"assigned": assigned, "skipped": len(results) - assigned, "results": results}


def change_supplier(tenant_id, assignment_id, supplier_code, updated_by):
    _validate_supplier(supplier_code)
    a = _require_assignment(tenant_id, assignment_id)
    if a.get("assignment_status") == "exported":
        raise HTTPException(
            status_code=409, detail="Cannot change supplier on an exported assignment"
        )
    conn = get_connection()
    try:
        if repo.duplicate_active_exists(
            conn, tenant_id, a["order_item_id"], supplier_code,
            exclude_assignment_id=assignment_id,
        ):
            raise HTTPException(
                status_code=409,
                detail="An active assignment for this supplier already exists",
            )
        repo.update_supplier(conn, tenant_id, assignment_id, supplier_code, updated_by)
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return _require_assignment(tenant_id, assignment_id)


def remove_assignment(tenant_id, assignment_id, deleted_by):
    a = _require_assignment(tenant_id, assignment_id)
    if a.get("assignment_status") == "exported":
        raise HTTPException(
            status_code=409, detail="Cannot remove an exported assignment"
        )
    conn = get_connection()
    try:
        repo.soft_delete(conn, tenant_id, assignment_id, deleted_by)
        repo.recompute_order_item(conn, tenant_id, a["order_item_id"])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"status": "removed", "assignment_id": assignment_id,
            "item": _require_item(tenant_id, a["order_item_id"])}
