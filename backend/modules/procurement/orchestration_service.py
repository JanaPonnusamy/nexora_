from __future__ import annotations

"""Procurement lifecycle orchestration (Phase 4).

Connects the pieces built in earlier phases — it adds NO business rules:

    Business Cycle -> Create Refresh -> Decision Engine (Phase 3)
                   -> Generate Working Order Items -> Publish

Reuses: repository (Cycle), vpl_repository (Refresh), decision_service (engine),
order_items_repository (working items). Business logic stays in the Decision
Engine; this layer only sequences and validates.
"""

import os
import threading
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
from modules.procurement import network_movement_service
from modules.procurement import vpl_history_repository
from modules.procurement import assignment_repository
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

def _is_unique_violation(exc):
    """pyodbc raises IntegrityError (SQLSTATE 23000) for a unique-index
    violation — matches the filtered unique index added by
    0029_refresh_idempotency_key.sql. Checked by class name/message content,
    not isinstance, so this has no hard import dependency on pyodbc here."""
    name = type(exc).__name__
    text = str(exc)
    return name == "IntegrityError" or "23000" in text or "duplicate key" in text.lower()


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

    # D5 — refresh retry returns/reuses the existing result for the same
    # logical request (owner-approved 2026-10-21: client-supplied
    # idempotency_key, not a parameter-dedup window). Feature-gated behind
    # PROCUREMENT_REFRESH_IDEMPOTENCY (default off): migration
    # 0029_refresh_idempotency_key.sql, which adds the column this check
    # reads, is NOT APPLIED — querying it unconditionally would break
    # create_refresh against the live, unmigrated schema.
    idempotency_enabled = os.environ.get("PROCUREMENT_REFRESH_IDEMPOTENCY") == "1"
    idempotency_key = payload.get("idempotency_key") if idempotency_enabled else None
    if idempotency_key:
        existing = refresh_repo.find_by_idempotency_key(tenant_id, cycle_id, idempotency_key)
        if existing:
            logger.info(
                "Refresh idempotency hit tenant=%s cycle=%s key=%s refresh=%s",
                tenant_id, cycle_id, idempotency_key, existing["refresh_id"],
            )
            return existing

    previous_refresh_id = (
        payload.get("previous_refresh_id")
        or cycle_repo.get_active_refresh_id(tenant_id, cycle_id)
    )

    # 1) Create the immutable Refresh header (reuses Phase 2). The name and
    #    per-cycle sequence number are server-authoritative — the Refresh number
    #    increments within the cycle and restarts at 1 for each new cycle.
    store_id = cycle.get("store_id")
    refresh_no = refresh_repo.next_refresh_no(tenant_id, cycle_id)
    try:
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
            "idempotency_key": idempotency_key,
        })
    except Exception as exc:
        # D5 concurrent-retry race: two callers both miss the
        # find_by_idempotency_key check above (neither has committed yet),
        # both attempt to insert the same (tenant_id, cycle_id,
        # idempotency_key) — the filtered unique index
        # (0029_refresh_idempotency_key.sql) rejects the second as a
        # constraint violation. Treat that specific case as "someone else
        # already created it" and return their row, not a 500.
        if idempotency_key and _is_unique_violation(exc):
            existing = refresh_repo.find_by_idempotency_key(tenant_id, cycle_id, idempotency_key)
            if existing:
                return existing
        raise
    refresh_id = refresh["refresh_id"]

    # 2) Run the completed Decision Engine (persists VPL, publishes Refresh,
    #    points the Cycle at it). Business rules are NOT duplicated here.
    engine = decision_service.generate_vpl(tenant_id, refresh_id)

    # 3) Generate Working Order Items from the VPL (suggested_qty > 0), bulk,
    #    then carry forward the previous Refresh's pending (Module 4).
    # Step 4 (VPL History) — feature-gated behind PROCUREMENT_VPL_HISTORY
    # (default off, same pattern as D3c/D5): migration
    # 0030_vpl_history_persistence.sql, which adds the tables this reads/writes,
    # is NOT APPLIED — running this unconditionally would 500 every refresh
    # against the live, unmigrated schema. When on, the PREVIOUS refresh's
    # working items + assignments are snapshotted into history in the SAME
    # transaction that deletes them via clear_working_items below, so a
    # rollback here leaves neither a partial history batch nor a deleted
    # working set — both-or-neither. Only writes a batch when there is a
    # previous refresh with items to snapshot (first refresh in a cycle has
    # nothing to archive).
    history_enabled = os.environ.get("PROCUREMENT_VPL_HISTORY") == "1"

    conn = get_connection()
    try:
        if history_enabled and previous_refresh_id and previous_refresh_id != refresh_id:
            previous_lines = vpl_history_repository.list_items_for_history(
                conn, tenant_id, previous_refresh_id
            )
            if previous_lines:
                previous_assignments = assignment_repository.list_by_refresh(
                    tenant_id, previous_refresh_id
                )
                assignments_by_item = {}
                for a in previous_assignments:
                    assignments_by_item.setdefault(a["order_item_id"], []).append(a)
                try:
                    vpl_history_repository.write_history_batch(
                        conn, tenant_id, store_id, cycle_id, previous_refresh_id,
                        refresh_id, previous_lines, assignments_by_item,
                        payload.get("created_by"),
                    )
                except Exception as exc:
                    # Retry-safe per vpl_history_repository's own contract: a
                    # second create_refresh call for the same (prev, new) pair
                    # hits the batch's unique index — that only happens if this
                    # exact successor was already archived (not a fresh retry
                    # path today, since refresh_id is freshly generated above),
                    # so treat it as "already archived" and continue rather
                    # than failing the whole refresh over a history write.
                    if not _is_unique_violation(exc):
                        raise
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

    # 5) Network Movement Intelligence — informational-only, tenant-wide cache
    #    (cross-store, not this Refresh's own data). Measured at ~230s for a
    #    real 6-store/54k-product tenant (store_metrics' 730-day scan is the
    #    cost, same query Product Intelligence already pays per store) — far
    #    too slow to run inline in the Refresh request/response cycle, so it is
    #    fired on a background thread and allowed to finish after the Refresh
    #    has already returned. Never allowed to fail OR delay the Refresh: this
    #    is a visibility feature layered on the completed, published pipeline,
    #    not part of the procurement-critical path.
    def _refresh_network_movement_async():
        try:
            network_movement_service.refresh_network_movement(tenant_id)
        except Exception:
            logger.exception(
                "Network movement refresh failed tenant=%s refresh=%s (non-fatal)",
                tenant_id, refresh_id,
            )

    threading.Thread(target=_refresh_network_movement_async, daemon=True).start()
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


# --------------------------------------------------------------------------
# Ensure-context — one-call "open the store, get a working refresh" for the
# single-screen buyer entry flow. No new concept: just get-or-create on top
# of the existing Cycle/Refresh primitives above, so the buyer never has to
# create or pick between them (VB.NET OrderManagement had no such step).
# --------------------------------------------------------------------------

def ensure_active_context(tenant_id: str, store_id: str, created_by=None):
    """Return {cycle, refresh} for the store, creating whichever is missing.

    Does NOT create a new refresh just because one is being asked for again —
    an existing active cycle with an existing current refresh is returned
    unchanged (no Decision Engine run, no new working items). A refresh is
    only generated the first time a store's active cycle has none yet.
    Mirrors the client-side "find active cycle, else open one" recipe already
    used by CycleRefreshConsolePage.runPipeline, but as a single idempotent
    server call for the plain single-store entry path instead of a bulk
    multi-store batch-refresh operation.
    """
    if not store_id:
        raise HTTPException(status_code=400, detail="store_id is required")

    cycle = cycle_repo.get_active_cycle(tenant_id, store_id)
    if cycle is None:
        cycle = create_business_cycle({
            "tenant_id": tenant_id,
            "store_id": store_id,
            "created_by": created_by,
        })

    refresh_id = cycle.get("active_refresh_id")
    if refresh_id:
        refresh = refresh_repo.get_vpl(tenant_id, refresh_id)
    else:
        refresh = None

    if refresh is None:
        result = create_refresh(tenant_id, cycle["cycle_id"], {
            "rolling_days": 90,
            "min_days": 13,
            "max_days": 18,
            "created_by": created_by,
        })
        refresh = refresh_repo.get_vpl(tenant_id, result["refresh_id"])
        # create_refresh may have archived the old cycle row's view of itself —
        # re-read so the returned cycle reflects the just-created refresh.
        cycle = cycle_repo.get_cycle(tenant_id, cycle["cycle_id"])

    return {"cycle": cycle, "refresh": refresh}


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
