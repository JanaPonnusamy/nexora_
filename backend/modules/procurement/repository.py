"""Data access for the Procurement module — Cycle.

Targets NEXORA_PLATFORM only. Every read/write is tenant-scoped and respects
soft delete (is_deleted = 0). Audit columns are stamped here so the service
layer stays free of SQL details.

One resource:
    procurement.procurement_cycles

The Workspace concept has been removed from the approved model.
"""

from config.database import get_connection
from modules.procurement._dbutil import (
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
    as_uid as _as_uid,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

# ==========================================================================
# Procurement Cycle
# ==========================================================================

def create_cycle(data):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO procurement.procurement_cycles
                (tenant_id, store_id, name, description, status,
                 start_date, end_date,
                 start_grn_number, start_sale_bill_number,
                 end_grn_number, end_sale_bill_number, created_by)
            OUTPUT INSERTED.cycle_id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["tenant_id"],
                data.get("store_id"),
                data["name"],
                data.get("description"),
                data.get("status", "DRAFT"),
                data.get("start_date"),
                data.get("end_date"),
                data.get("start_grn_number"),
                data.get("start_sale_bill_number"),
                data.get("end_grn_number"),
                data.get("end_sale_bill_number"),
                _as_uid(data.get("created_by")),
            ),
        )
        cycle_id = str(cursor.fetchone()[0])
        conn.commit()
        return get_cycle(data["tenant_id"], cycle_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_cycle(tenant_id, cycle_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cycle_id, tenant_id, store_id, name, description, status,
                   start_date, end_date,
                   start_grn_number, start_sale_bill_number,
                   end_grn_number, end_sale_bill_number, active_refresh_id,
                   created_at, created_by, updated_at, updated_by
            FROM procurement.procurement_cycles
            WHERE cycle_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (cycle_id, tenant_id),
        )
        rows = _rows_to_dicts(cursor)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


def list_cycles(tenant_id, status, search, page, page_size, store_id=None):
    where = ["tenant_id = ?", "is_deleted = 0"]
    params = [tenant_id]

    # Procurement is executed per-store: scope the listing to one store so the
    # admin never sees (or acts on) another store's cycles.
    if store_id:
        where.append("store_id = ?")
        params.append(store_id)
    if status is not None:
        where.append("status = ?")
        params.append(status)
    if search:
        where.append("(name LIKE ? OR description LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size

    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            f"SELECT COUNT(*) FROM procurement.procurement_cycles "
            f"WHERE {where_sql}",
            params,
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT cycle_id, tenant_id, store_id, name, description, status,
                   start_date, end_date,
                   start_grn_number, start_sale_bill_number,
                   end_grn_number, end_sale_bill_number, active_refresh_id,
                   created_at, created_by, updated_at, updated_by
            FROM procurement.procurement_cycles
            WHERE {where_sql}
            ORDER BY created_at DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            params + [offset, page_size],
        )
        items = [_stringify(r) for r in _rows_to_dicts(cursor)]
        return items, total
    finally:
        conn.close()


def update_cycle(tenant_id, cycle_id, data):
    fields = []
    params = []
    for column in (
        "name", "description", "status", "start_date", "end_date",
        "start_grn_number", "start_sale_bill_number",
        "end_grn_number", "end_sale_bill_number",
    ):
        if column in data:
            fields.append(f"{column} = ?")
            params.append(data[column])

    if not fields:
        return get_cycle(tenant_id, cycle_id)

    fields.append("updated_at = GETDATE()")
    fields.append("updated_by = ?")
    params.append(data.get("updated_by"))

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE procurement.procurement_cycles
            SET {", ".join(fields)}
            WHERE cycle_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            params + [cycle_id, tenant_id],
        )
        affected = cursor.rowcount
        conn.commit()
        if affected == 0:
            return None
        return get_cycle(tenant_id, cycle_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_cycle(tenant_id, cycle_id, deleted_by):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE procurement.procurement_cycles
            SET is_deleted = 1,
                deleted_at = GETDATE(),
                deleted_by = ?
            WHERE cycle_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (deleted_by, cycle_id, tenant_id),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def active_cycle_exists(tenant_id, store_id=None):
    """True when an ACTIVE (non-deleted) cycle already exists for the tenant
    (optionally scoped to a store). Enforces the single-active-cycle rule
    (PR-BR-022 / Ratified Decision 1)."""
    where = ["tenant_id = ?", "is_deleted = 0", "status = 'ACTIVE'"]
    params = [tenant_id]
    if store_id is not None:
        where.append("store_id = ?")
        params.append(store_id)
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT 1 FROM procurement.procurement_cycles "
            f"WHERE {' AND '.join(where)}",
            params,
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def get_active_refresh_id(tenant_id, cycle_id):
    """The cycle's current active_refresh_id (or None)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT active_refresh_id FROM procurement.procurement_cycles
            WHERE cycle_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (cycle_id, tenant_id),
        )
        row = cursor.fetchone()
        return str(row[0]) if row and row[0] is not None else None
    finally:
        conn.close()


def refreshing_in_progress(tenant_id, cycle_id):
    """True when a Refresh for the cycle is mid-generation ('Refreshing')."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM procurement.procurement_refreshes
            WHERE tenant_id = ? AND cycle_id = ? AND is_deleted = 0
              AND snapshot_status = 'Refreshing'
            """,
            (tenant_id, cycle_id),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


def cycle_close_blockers(tenant_id, cycle_id):
    """Read-only pre-close checks. Returns the count of open work that must be
    resolved before an ACTIVE cycle can be closed. Purely a guard — no writes,
    no workflow change. Scoped to the cycle via cycle_id (present on refreshes
    and assignments).

    Keys:
      active_refreshes — a Refresh is still generating (snapshot_status
                         'Refreshing')
      pending_exports  — supplier assignments allocated but not yet exported
      pending_grns     — Refreshes with exported lines whose GRN isn't completed
      pending_receive  — order items with quantity still to be received
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) FROM procurement.procurement_refreshes
            WHERE tenant_id = ? AND cycle_id = ? AND is_deleted = 0
              AND snapshot_status = 'Refreshing'
            """,
            (tenant_id, cycle_id),
        )
        active_refreshes = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM procurement.procurement_order_item_assignments
            WHERE tenant_id = ? AND cycle_id = ? AND is_deleted = 0
              AND assignment_status = 'draft'
              AND supplier_code IS NOT NULL AND assigned_qty > 0
            """,
            (tenant_id, cycle_id),
        )
        pending_exports = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM procurement.procurement_refreshes r
            WHERE r.tenant_id = ? AND r.cycle_id = ? AND r.is_deleted = 0
              AND r.grn_completed_at IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM procurement.procurement_order_item_assignments a
                  WHERE a.tenant_id = r.tenant_id AND a.refresh_id = r.refresh_id
                    AND a.is_deleted = 0
                    AND a.assignment_status IN ('exported', 'partial_received')
              )
            """,
            (tenant_id, cycle_id),
        )
        pending_grns = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT COUNT(*) FROM procurement.procurement_order_items
            WHERE tenant_id = ? AND cycle_id = ? AND is_deleted = 0
              AND remaining_qty > 0 AND item_status <> 'skipped'
              AND (pending_status IS NULL
                   OR pending_status NOT IN ('finalized', 'carried'))
            """,
            (tenant_id, cycle_id),
        )
        pending_receive = cursor.fetchone()[0]

        return {
            "active_refreshes": active_refreshes,
            "pending_exports": pending_exports,
            "pending_grns": pending_grns,
            "pending_receive": pending_receive,
        }
    finally:
        conn.close()


def refresh_ids_for_cycle(tenant_id, cycle_id):
    """All live Refresh ids for the cycle (used to reconcile on close)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT refresh_id FROM procurement.procurement_refreshes
            WHERE tenant_id = ? AND cycle_id = ? AND is_deleted = 0
            """,
            (tenant_id, cycle_id),
        )
        return [str(r[0]) for r in cursor.fetchall()]
    finally:
        conn.close()


def pending_item_count(tenant_id, cycle_id):
    """Count of unresolved pending items across the cycle (remaining to receive,
    not skipped, not already finalized/cleared/carried). Drives the close
    confirmation prompt."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) FROM procurement.procurement_order_items
            WHERE tenant_id = ? AND cycle_id = ? AND is_deleted = 0
              AND remaining_qty > 0 AND item_status <> 'skipped'
              AND (pending_status IS NULL
                   OR pending_status NOT IN ('finalized', 'cleared', 'carried'))
            """,
            (tenant_id, cycle_id),
        )
        return cursor.fetchone()[0]
    finally:
        conn.close()


def clear_all_pending(tenant_id, cycle_id, cleared_by):
    """Resolve every unresolved pending item in the cycle as 'cleared' — used
    when a cycle is closed WITHOUT carrying pending into the next cycle. Nothing
    is carried forward; the next cycle starts fresh."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE procurement.procurement_order_items
            SET pending_status = 'cleared',
                reviewed_by = ?, reviewed_at = GETDATE(), updated_at = GETDATE()
            WHERE tenant_id = ? AND cycle_id = ? AND is_deleted = 0
              AND remaining_qty > 0 AND item_status <> 'skipped'
              AND (pending_status IS NULL
                   OR pending_status NOT IN ('finalized', 'cleared', 'carried'))
            """,
            (_as_uid(cleared_by), tenant_id, cycle_id),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def close_cycle(tenant_id, cycle_id, end_grn, end_sale_bill, closed_by):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE procurement.procurement_cycles
            SET status = 'Closed',
                end_grn_number = ?, end_sale_bill_number = ?,
                closed_at = GETDATE(), updated_by = ?, updated_at = GETDATE()
            WHERE cycle_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (end_grn, end_sale_bill, _as_uid(closed_by), cycle_id, tenant_id),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cycle_exists(tenant_id, cycle_id):
    """True when the cycle is live and belongs to the given tenant."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM procurement.procurement_cycles
            WHERE cycle_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (cycle_id, tenant_id),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()
