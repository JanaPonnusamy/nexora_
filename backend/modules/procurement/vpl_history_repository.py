"""Durable VPL History persistence (Step 4).

Implements the "Revised data contract" and "Concurrency design" accepted in
principle in PHASE_2_VPL_HISTORY.md, against migration
0030_vpl_history_persistence.sql (NOT APPLIED). This is a NEW, separate
module from vpl_history.py (Cursor-owned, in-memory prototype) — it does not
edit that file or its router. It is not yet called by orchestration_service
or any live route; wiring it into the real create_refresh pipeline is a
separate, flag-gated follow-up once 0030 is applied (same pattern as D3c's
PROCUREMENT_RARE_MOVER_ENFORCEMENT and D5's PROCUREMENT_REFRESH_IDEMPOTENCY).

Writes a history batch + its lines + each line's assignment children as one
caller-owned transaction (same get_connection()/commit()/rollback() pattern
used throughout this module) — a failure partway through leaves no partial
batch, since nothing commits until the whole snapshot is written.
"""

from modules.procurement._dbutil import as_uid as _as_uid, rows_to_dicts as _rows_to_dicts


def write_history_batch(conn, tenant_id, store_id, cycle_id, source_refresh_id,
                         successor_refresh_id, lines, assignments_by_order_item_id,
                         created_by, rule_snapshot_id=None):
    """Snapshot one refresh's working set (order items + their assignments)
    into history, keyed by (source_order_item_id), as a copy — not a live
    foreign key. `lines` is a list of procurement_order_items-shaped dicts
    (as returned by workspace_repository.get_item / list_items).
    `assignments_by_order_item_id` maps order_item_id -> list of
    assignment dicts (assignment_id, supplier_code, assigned_qty,
    assignment_status).

    Retry-safe: a second call with the same (tenant_id, source_refresh_id,
    successor_refresh_id) hits the batch's unique index and raises — the
    caller should treat that as "already archived," not retry blindly (same
    idempotency posture as D5's refresh retry).
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO procurement.vpl_history_batch
            (tenant_id, store_id, cycle_id, source_refresh_id,
             successor_refresh_id, rule_snapshot_id, line_count, created_by)
        OUTPUT INSERTED.history_id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (tenant_id, store_id, cycle_id, source_refresh_id,
         successor_refresh_id, rule_snapshot_id, len(lines), _as_uid(created_by)),
    )
    history_id = str(cursor.fetchone()[0])

    for line in lines:
        order_item_id = line["order_item_id"]
        cursor.execute(
            """
            INSERT INTO procurement.vpl_history_line
                (history_id, source_order_item_id, tenant_id, store_id, cycle_id,
                 source_refresh_id, product_id, product_code,
                 suggested_qty, final_qty, manual_override, item_status,
                 skip_reason, reviewed_by, reviewed_at, reason_code,
                 row_version, carried_forward)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                history_id, order_item_id, tenant_id, store_id, cycle_id,
                source_refresh_id, line.get("product_id"), line.get("product_code"),
                line.get("suggested_qty"), line.get("final_qty"),
                1 if line.get("manual_override") else 0, line.get("item_status"),
                line.get("skip_reason"), _as_uid(line.get("reviewed_by")),
                line.get("reviewed_at"), line.get("reason_code"),
                line.get("row_version") or 1, 1 if line.get("carried_forward") else 0,
            ),
        )
        for assignment in assignments_by_order_item_id.get(order_item_id, []):
            cursor.execute(
                """
                INSERT INTO procurement.vpl_history_assignment
                    (history_id, source_assignment_id, source_order_item_id,
                     tenant_id, store_id, cycle_id, source_refresh_id,
                     supplier_code, assigned_qty, assignment_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    history_id, assignment["assignment_id"], order_item_id,
                    tenant_id, store_id, cycle_id, source_refresh_id,
                    assignment.get("supplier_code"), assignment.get("assigned_qty"),
                    assignment.get("assignment_status"),
                ),
            )

    return history_id


def list_items_for_history(conn, tenant_id, refresh_id):
    """Every live working item for one Refresh, shaped for write_history_batch's
    `lines` argument. Runs on the caller's own transaction (same connection
    create_refresh already holds) so the read sees the pre-delete state —
    this must be called before order_items_repository.clear_working_items."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT order_item_id, product_id, product_code,
               suggested_qty, final_qty, manual_override, item_status,
               skip_reason, reviewed_by, reviewed_at,
               row_version, is_manual
        FROM procurement.procurement_order_items
        WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0
        """,
        (tenant_id, refresh_id),
    )
    rows = _rows_to_dicts(cursor)
    for row in rows:
        row["carried_forward"] = bool(row.pop("is_manual"))
    return rows


def list_batches(tenant_id, store_id, limit=10):
    from config.database import get_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT TOP (?) history_id, tenant_id, store_id, cycle_id,
                   source_refresh_id, successor_refresh_id, rule_snapshot_id,
                   line_count, created_at, created_by
            FROM procurement.vpl_history_batch
            WHERE tenant_id = ? AND store_id = ?
            ORDER BY created_at DESC
            """,
            (limit, tenant_id, store_id),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def get_batch_lines(tenant_id, history_id):
    from config.database import get_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT source_order_item_id, product_id, product_code,
                   suggested_qty, final_qty, manual_override, item_status,
                   skip_reason, reviewed_by, reviewed_at, reason_code,
                   row_version, carried_forward, copied_at
            FROM procurement.vpl_history_line
            WHERE tenant_id = ? AND history_id = ?
            """,
            (tenant_id, history_id),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


def get_line_assignments(tenant_id, history_id, source_order_item_id):
    from config.database import get_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT source_assignment_id, supplier_code, assigned_qty,
                   assignment_status, copied_at
            FROM procurement.vpl_history_assignment
            WHERE tenant_id = ? AND history_id = ? AND source_order_item_id = ?
            """,
            (tenant_id, history_id, source_order_item_id),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Removed (manual-review) lines
# --------------------------------------------------------------------------

def upsert_removed_line(conn, tenant_id, store_id, cycle_id, product_id, product_code,
                         originating_refresh_id, originating_cycle_id,
                         removed_during_refresh_id, final_qty, manual_override,
                         override_reason, supplier_code, assigned_qty, removed_by):
    """Records a manually-touched line whose product dropped out of the
    latest generation (D3c-adjacent "Finding 2" / Option A, approved in
    principle). At most one ACTIVE (restored_at IS NULL) row per
    (tenant_id, store_id, cycle_id, product_id) — enforced by the filtered
    unique index in 0030, not re-checked here; a duplicate active insert
    fails closed with a constraint violation rather than silently
    overwriting the prior removal episode.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO procurement.vpl_removed_line
            (tenant_id, store_id, cycle_id, product_id, product_code,
             originating_refresh_id, originating_cycle_id, removed_during_refresh_id,
             final_qty, manual_override, override_reason, supplier_code,
             assigned_qty, removed_by)
        OUTPUT INSERTED.removed_id
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tenant_id, store_id, cycle_id, product_id, product_code,
            originating_refresh_id, originating_cycle_id, removed_during_refresh_id,
            final_qty, 1 if manual_override else 0, override_reason, supplier_code,
            assigned_qty, _as_uid(removed_by),
        ),
    )
    return str(cursor.fetchone()[0])


def restore_removed_line(conn, tenant_id, store_id, cycle_id, product_id, restored_by):
    """Clears the active removed row (restored_at set, not hard-deleted) in
    the same transaction the caller uses to write the reappeared product's
    new order item — the episode stays queryable, only its "active" status
    changes. Returns the restored row (for the caller to copy its manual
    fields onto the new order item) or None if no active row exists."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT removed_id, final_qty, manual_override, override_reason,
               supplier_code, assigned_qty
        FROM procurement.vpl_removed_line
        WHERE tenant_id = ? AND store_id = ? AND cycle_id = ? AND product_id = ?
          AND restored_at IS NULL
        """,
        (tenant_id, store_id, cycle_id, product_id),
    )
    row = cursor.fetchone()
    if not row:
        return None
    removed_id = row[0]
    cursor.execute(
        """
        UPDATE procurement.vpl_removed_line
        SET restored_at = GETDATE(), restored_by = ?
        WHERE removed_id = ? AND restored_at IS NULL
        """,
        (_as_uid(restored_by), removed_id),
    )
    if cursor.rowcount == 0:
        # Someone else restored it between the SELECT and this UPDATE —
        # fail closed rather than double-restore.
        return None
    return {
        "removed_id": str(removed_id), "final_qty": row[1],
        "manual_override": bool(row[2]), "override_reason": row[3],
        "supplier_code": row[4], "assigned_qty": row[5],
    }


def list_active_removed_lines(tenant_id, store_id, cycle_id):
    from config.database import get_connection
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT removed_id, product_id, product_code, originating_refresh_id,
                   originating_cycle_id, removed_during_refresh_id,
                   final_qty, manual_override, override_reason,
                   supplier_code, assigned_qty, removed_at, removed_by
            FROM procurement.vpl_removed_line
            WHERE tenant_id = ? AND store_id = ? AND cycle_id = ? AND restored_at IS NULL
            """,
            (tenant_id, store_id, cycle_id),
        )
        return _rows_to_dicts(cursor)
    finally:
        conn.close()
