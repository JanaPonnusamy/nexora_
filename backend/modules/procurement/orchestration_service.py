from __future__ import annotations

"""Procurement lifecycle orchestration (Phase 4).

Connects the pieces built in earlier phases — it adds NO business rules:

    Business Cycle -> Create Refresh -> Decision Engine (Phase 3)
                   -> Generate Working Order Items -> Publish

Reuses: repository (Cycle), vpl_repository (Refresh), decision_service (engine),
order_items_repository (working items). Business logic stays in the Decision
Engine; this layer only sequences and validates.
"""

from datetime import date

from fastapi import HTTPException

from config.database import get_connection
from modules.procurement import repository as cycle_repo
from modules.procurement import vpl_repository as refresh_repo
from modules.procurement import order_items_repository as items_repo
from modules.procurement import decision_service
from modules.procurement import decision_rules as rules
from modules.procurement import comparison_service
from modules.procurement import reconciliation_service
from modules.procurement import supplier_exclusion_repository as exclusion_repo
from modules.procurement import platform_source_repository as platform_repo
from repositories.store_repository import StoreRepository

import logging

logger = logging.getLogger("procurement.orchestration")


# --------------------------------------------------------------------------
# Naming convention (server-authoritative — see Cycle/Refresh naming rules)
#
#   Cycle    : "<Store Code> - <YYYY-MM-DD> - Cycle"
#   Refresh  : "<Store Code> - <YYYY-MM-DD> - Refresh <No>"
#
# The short store CODE (e.g. NMA, NMW) is used — not the full store name — so
# names stay compact in dropdowns and console columns. Generated here so EVERY
# entry point (console, launcher, auto-reopen on close) yields identical,
# self-describing names — no generic "Refresh"/"Cycle" ever.
# --------------------------------------------------------------------------

def _store_abbrev(store_id) -> str:
    """Short store code (NMA, NMW, …) for names; falls back to name, then id."""
    if not store_id:
        return "Store"
    row = StoreRepository().get_by_id(store_id)
    if row is None:
        return str(store_id)
    code = getattr(row, "store_code", None)
    name = getattr(row, "store_name", None)
    return (code or name or str(store_id)).strip()


def cycle_name(store_id, on: date | None = None) -> str:
    return f"{_store_abbrev(store_id)} - {(on or date.today()):%Y-%m-%d} - Cycle"


def refresh_name(store_id, refresh_no: int, on: date | None = None) -> str:
    return f"{_store_abbrev(store_id)} - {(on or date.today()):%Y-%m-%d} - Refresh {refresh_no}"


# --------------------------------------------------------------------------
# Business Cycle
# --------------------------------------------------------------------------

def create_business_cycle(payload: dict):
    """Open an ACTIVE Business Cycle after validating the platform preconditions.

    Validates: user identity present (RBAC gate — see note), store exists, and
    no ACTIVE cycle already exists. Captures the Start GRN / Start Sale Bill.
    """
    tenant_id = payload["tenant_id"]
    store_id = payload.get("store_id")

    # Permission gate. Procurement defines no roles of its own (PR-BR-017/019):
    # cycle.create is a platform RBAC permission. Until the auth context is wired
    # into these endpoints, we require the acting user id; the platform RBAC check
    # plugs in here.
    if not payload.get("created_by"):
        raise HTTPException(
            status_code=403,
            detail="created_by (user) is required to open a Business Cycle",
        )

    # Procurement is store-based: a cycle must belong to exactly one store.
    if not store_id:
        raise HTTPException(status_code=400, detail="store_id is required to open a Business Cycle")
    # Store must exist (PR-BR-019 precondition).
    if StoreRepository().get_by_id(store_id) is None:
        raise HTTPException(status_code=400, detail="store_id does not exist")

    # Only one ACTIVE cycle at a time (PR-BR-022 / Ratified Decision 1).
    if cycle_repo.active_cycle_exists(tenant_id, store_id):
        raise HTTPException(
            status_code=409,
            detail="An ACTIVE Business Cycle already exists",
        )

    data = dict(payload)
    data["status"] = "ACTIVE"
    # Server-authoritative name — never trust a client-supplied/generic name.
    data["name"] = cycle_name(store_id)
    cycle = cycle_repo.create_cycle(data)
    logger.info("Cycle opened tenant=%s cycle=%s store=%s by=%s",
                tenant_id, cycle.get("cycle_id"), store_id, payload.get("created_by"))
    return cycle


# --------------------------------------------------------------------------
# Refresh (full orchestration)
# --------------------------------------------------------------------------

def _validate_parameters(rolling_days, min_days, max_days):
    params = rules.DecisionParameters(
        rolling_days=rolling_days or 90, min_days=min_days, max_days=max_days
    )
    try:
        params.validate()
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid refresh parameters: {exc}"
        )
    return params


def create_refresh(tenant_id: str, cycle_id: str, payload: dict):
    """Create an immutable Refresh and run the full pipeline.

    Stores snapshot parameters -> runs the Decision Engine (VPL) -> generates
    Working Order Items -> publishes. The prior active Refresh is archived.
    """
    cycle = cycle_repo.get_cycle(tenant_id, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    if cycle.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=409, detail="Refresh requires an ACTIVE cycle"
        )

    _validate_parameters(
        payload.get("rolling_days"), payload.get("min_days"), payload.get("max_days")
    )

    previous_refresh_id = (
        payload.get("previous_refresh_id")
        or cycle_repo.get_active_refresh_id(tenant_id, cycle_id)
    )

    # 1) Create the immutable Refresh header (reuses Phase 2). The name and
    #    per-cycle sequence number are server-authoritative — the Refresh number
    #    increments within the cycle and restarts at 1 for each new cycle.
    store_id = cycle.get("store_id")
    refresh_no = refresh_repo.next_refresh_no(tenant_id, cycle_id)
    refresh = refresh_repo.create_vpl({
        "tenant_id": tenant_id,
        "cycle_id": cycle_id,
        "store_id": store_id,
        "snapshot_name": refresh_name(store_id, refresh_no),
        "refresh_no": refresh_no,
        "rolling_days": payload.get("rolling_days"),
        "min_days": payload.get("min_days"),
        "max_days": payload.get("max_days"),
        "previous_refresh_id": previous_refresh_id,
        "snapshot_grn_number": payload.get("snapshot_grn_number"),
        "snapshot_sale_bill_number": payload.get("snapshot_sale_bill_number"),
        "sync_execution_id": payload.get("sync_execution_id"),
        "created_by": payload.get("created_by"),
    })
    refresh_id = refresh["refresh_id"]

    # 2) Run the completed Decision Engine (persists VPL, publishes Refresh,
    #    points the Cycle at it). Business rules are NOT duplicated here.
    engine = decision_service.generate_vpl(tenant_id, refresh_id)

    # 3) Generate Working Order Items from the VPL (suggested_qty > 0), bulk,
    #    then carry forward the previous Refresh's pending (Module 4).
    conn = get_connection()
    try:
        items_repo.clear_working_items(conn, tenant_id, refresh_id)
        working_items = items_repo.generate_working_items(
            conn, tenant_id, refresh_id,
            cycle.get("store_id"), payload.get("created_by"),
        )
        items_repo.carry_forward_skips(
            conn, tenant_id, previous_refresh_id, refresh_id, cycle.get("store_id"),
        )
        carried = comparison_service.carry_forward(
            conn, tenant_id, previous_refresh_id,
            {"refresh_id": refresh_id, "cycle_id": cycle_id,
             "store_id": cycle.get("store_id")},
            payload.get("created_by"),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # 4) Archive the previous Refresh (previous CURRENT -> historical). A refresh
    #    the user explicitly Closed keeps that status — never downgrade it.
    if previous_refresh_id and previous_refresh_id != refresh_id:
        prev = refresh_repo.get_vpl(tenant_id, previous_refresh_id)
        if (prev or {}).get("snapshot_status") != "Closed":
            refresh_repo.set_status(
                tenant_id, previous_refresh_id, "Archived", payload.get("created_by")
            )

    logger.info(
        "Refresh created tenant=%s cycle=%s refresh=%s products=%s working_items=%s "
        "carried=%s prev=%s", tenant_id, cycle_id, refresh_id,
        engine["generated_product_count"], working_items, carried, previous_refresh_id,
    )
    return {
        "refresh_id": refresh_id,
        "cycle_id": cycle_id,
        "status": engine["status"],
        "previous_refresh_id": previous_refresh_id,
        "generated_product_count": engine["generated_product_count"],
        "included_count": engine["included_count"],
        "excluded_count": engine["excluded_count"],
        "working_item_count": working_items,
        "carried_forward_count": carried,
        "parameters": engine["parameters"],
    }


def close_refresh(tenant_id: str, refresh_id: str, closed_by=None):
    """Lock a Refresh as 'Closed' (read-only) WITHOUT touching the cycle.

    Used by the console's "Close Refresh" action: the current refresh is closed
    and a fresh Refresh N+1 is generated in the SAME open cycle. Idempotent —
    closing an already-closed refresh is a no-op.
    """
    refresh = refresh_repo.get_vpl(tenant_id, refresh_id)
    if not refresh:
        raise HTTPException(status_code=404, detail="Refresh not found")
    if (refresh.get("snapshot_status") or "") != "Closed":
        refresh_repo.set_status(tenant_id, refresh_id, "Closed", closed_by)
        logger.info("Refresh closed tenant=%s refresh=%s by=%s",
                    tenant_id, refresh_id, closed_by)
    return refresh_repo.get_vpl(tenant_id, refresh_id)


# --------------------------------------------------------------------------
# Cycle closing (Module 5)
# --------------------------------------------------------------------------

def close_cycle(tenant_id, cycle_id, closed_by, force=False):
    """Close a cycle and roll straight into a fresh one.

    Flow (workflow agreed with the business):
      1. A Refresh mid-generation is a hard stop — never interruptible.
      2. Run GRN reconciliation over the latest synced purchases so received /
         remaining quantities are current (no manual GRN entry).
      3. If unresolved pending items remain and the caller has not confirmed,
         return ``status='pending_confirm'`` so the UI can prompt.
      4. On confirm (``force``): clear all pending WITHOUT carrying anything
         forward, stamp End GRN / End Sale Bill read from synced data, close the
         cycle, then auto-open a fresh ACTIVE cycle for the same store.
    """
    cycle = cycle_repo.get_cycle(tenant_id, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    if (cycle.get("status") or "").upper() == "CLOSED":
        raise HTTPException(status_code=409, detail="Cycle is already closed")

    store_id = cycle.get("store_id")

    # 1. Hard stop: a Refresh still generating cannot be interrupted.
    blockers = cycle_repo.cycle_close_blockers(tenant_id, cycle_id)
    if blockers["active_refreshes"]:
        raise HTTPException(
            status_code=409,
            detail="Cannot close: a Refresh is still generating. "
                   "Wait for it to finish, then close.",
        )

    # 2. Reconcile each Refresh against the latest synced receipts.
    for refresh_id in cycle_repo.refresh_ids_for_cycle(tenant_id, cycle_id):
        try:
            reconciliation_service.reconcile(tenant_id, refresh_id, store_id)
        except Exception:
            logger.exception(
                "Reconcile failed on close tenant=%s cycle=%s refresh=%s",
                tenant_id, cycle_id, refresh_id,
            )

    # 3. Pending confirmation gate.
    pending_count = cycle_repo.pending_item_count(tenant_id, cycle_id)
    if pending_count > 0 and not force:
        return {
            "status": "pending_confirm",
            "cycle_id": str(cycle_id),
            "pending_count": pending_count,
            "message": (
                f"{pending_count} pending item(s) still available. "
                "Closing will clear them (they will NOT be carried forward) "
                "and start a fresh cycle. Close anyway?"
            ),
        }

    # 4a. Record next-cycle supplier exclusions from any unresolved
    #     partial/not-available supplier replies, then clear all pending — no
    #     carry-forward into the next cycle.
    conn = get_connection()
    try:
        excluded = exclusion_repo.record_exclusions_from_replies(conn, tenant_id, cycle_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    if excluded:
        logger.info("Supplier exclusions recorded tenant=%s cycle=%s count=%s",
                    tenant_id, cycle_id, excluded)

    cleared = 0
    if pending_count > 0:
        cleared = cycle_repo.clear_all_pending(tenant_id, cycle_id, closed_by)

    # 4b. End GRN / End Sale Bill from synced data (no manual entry).
    end_grn = platform_repo.read_last_grn(tenant_id, store_id) if store_id else None
    end_bill = platform_repo.read_last_sale_bill(tenant_id, store_id) if store_id else None

    # 4c. Close the cycle.
    if not cycle_repo.close_cycle(tenant_id, cycle_id, end_grn, end_bill, closed_by):
        raise HTTPException(status_code=404, detail="Cycle not found")
    logger.info(
        "Cycle closed tenant=%s cycle=%s by=%s cleared=%s end_grn=%s end_bill=%s",
        tenant_id, cycle_id, closed_by, cleared, end_grn, end_bill,
    )

    # 4d. Auto-open a fresh ACTIVE cycle for the same store; carry the boundary
    #     numbers forward as the new cycle's start (continuity, not pending).
    new_cycle = cycle_repo.create_cycle({
        "tenant_id": tenant_id,
        "store_id": store_id,
        "name": cycle_name(store_id),
        "description": None,
        "status": "ACTIVE",
        "start_grn_number": end_grn,
        "start_sale_bill_number": end_bill,
        "created_by": closed_by,
    })
    logger.info("Fresh cycle opened tenant=%s cycle=%s store=%s",
                tenant_id, new_cycle.get("cycle_id"), store_id)

    return {
        "status": "closed",
        "cycle": cycle_repo.get_cycle(tenant_id, cycle_id),
        "new_cycle": new_cycle,
        "pending_cleared": cleared,
        "end_grn_number": end_grn,
        "end_sale_bill_number": end_bill,
    }
