"""Data access for the Refresh header and its Virtual Product List.

Targets NEXORA_PLATFORM only. Every read/write is tenant-scoped. The Refresh
header (procurement_refreshes, PK refresh_id) honours soft delete
(is_deleted = 0 = live). Detail rows live in procurement_virtual_products
(PK virtual_product_id) and reference the owning Refresh via refresh_id.

Stores product identity, snapshot metadata and the immutable snapshot
parameters — no calculated business fields. The Workspace concept has been
removed.
"""

from config.database import get_connection
from modules.procurement._dbutil import (
    as_uid as _as_uid,
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# integrity checks (used by service validation)
# --------------------------------------------------------------------------

def product_in_vpl(tenant_id, refresh_id, product_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM procurement.procurement_virtual_products
            WHERE refresh_id = ? AND product_id = ? AND tenant_id = ?
            """,
            (refresh_id, product_id, tenant_id),
        )
        return cursor.fetchone() is not None
    finally:
        conn.close()


# ==========================================================================
# Refresh header (procurement_refreshes)
# ==========================================================================

# Columns returned for a Refresh header (single source of truth for SELECTs).
_REFRESH_COLUMNS = """
    refresh_id, tenant_id, cycle_id, store_id,
    snapshot_name, snapshot_status,
    refresh_no, rolling_days, min_days, max_days,
    previous_refresh_id, snapshot_grn_number, snapshot_sale_bill_number,
    sync_execution_id, generated_product_count,
    generation_started_at, generation_completed_at, remarks,
    last_snapshot_on, last_snapshot_by,
    created_by, created_at, updated_by, updated_at
"""


def create_vpl(data):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO procurement.procurement_refreshes
                (tenant_id, cycle_id, store_id,
                 snapshot_name, snapshot_status, refresh_no,
                 rolling_days, min_days, max_days, previous_refresh_id,
                 snapshot_grn_number, snapshot_sale_bill_number,
                 sync_execution_id, created_by)
            OUTPUT INSERTED.refresh_id
            VALUES (?, ?, ?, ?, 'Draft', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["tenant_id"],
                data["cycle_id"],
                data.get("store_id"),
                data["snapshot_name"],
                data.get("refresh_no"),
                data.get("rolling_days"),
                data.get("min_days"),
                data.get("max_days"),
                data.get("previous_refresh_id"),
                data.get("snapshot_grn_number"),
                data.get("snapshot_sale_bill_number"),
                data.get("sync_execution_id"),
                _as_uid(data.get("created_by")),
            ),
        )
        refresh_id = str(cursor.fetchone()[0])
        conn.commit()
        return get_vpl(data["tenant_id"], refresh_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def next_refresh_no(tenant_id, cycle_id):
    """Next sequential Refresh number WITHIN the cycle (1-based). Numbering
    restarts at 1 for every new cycle — see the Refresh naming convention."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT MAX(refresh_no) FROM procurement.procurement_refreshes
            WHERE tenant_id = ? AND cycle_id = ? AND is_deleted = 0
            """,
            (tenant_id, cycle_id),
        )
        row = cursor.fetchone()
        return (row[0] or 0) + 1 if row else 1
    finally:
        conn.close()


def get_vpl(tenant_id, refresh_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {_REFRESH_COLUMNS}
            FROM procurement.procurement_refreshes
            WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (refresh_id, tenant_id),
        )
        rows = _rows_to_dicts(cursor)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


def list_vpls(tenant_id, cycle_id, store_id,
              status, search, page, page_size):
    where = ["tenant_id = ?", "is_deleted = 0"]
    params = [tenant_id]

    if cycle_id is not None:
        where.append("cycle_id = ?")
        params.append(cycle_id)
    if store_id is not None:
        where.append("store_id = ?")
        params.append(store_id)
    if status is not None:
        where.append("snapshot_status = ?")
        params.append(status)
    if search:
        where.append("snapshot_name LIKE ?")
        params.append(f"%{search}%")

    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) FROM "
            f"procurement.procurement_refreshes WHERE {where_sql}",
            params,
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT {_REFRESH_COLUMNS}
            FROM procurement.procurement_refreshes
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


def set_status(tenant_id, refresh_id, new_status, updated_by):
    """Transition snapshot_status and stamp audit. Returns affected rows."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE procurement.procurement_refreshes
            SET snapshot_status = ?,
                updated_by = ?,
                updated_at = GETDATE()
            WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (new_status, _as_uid(updated_by), refresh_id, tenant_id),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_vpl(tenant_id, refresh_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE procurement.procurement_refreshes
            SET is_deleted = 1, deleted_at = GETDATE()
            WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (refresh_id, tenant_id),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ==========================================================================
# Virtual Products (detail)
# ==========================================================================

_PRODUCT_COLUMNS = """
    virtual_product_id, tenant_id, cycle_id, refresh_id, product_id,
    product_code, product_name, manufacturer_id, category_id,
    schedule_type, unit, is_active, snapshot_version,
    created_at, updated_at
"""


def add_product(tenant_id, vpl, data):
    """vpl is the resolved Refresh header dict (supplies cycle_id, refresh_id)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO procurement.procurement_virtual_products
                (tenant_id, cycle_id, refresh_id, product_id,
                 product_code, product_name, manufacturer_id, category_id,
                 schedule_type, unit, is_active, snapshot_version)
            OUTPUT INSERTED.virtual_product_id
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                vpl["cycle_id"],
                vpl["refresh_id"],
                data["product_id"],
                data.get("product_code"),
                data.get("product_name"),
                data.get("manufacturer_id"),
                data.get("category_id"),
                data.get("schedule_type"),
                data.get("unit"),
                data.get("is_active", True),
                data.get("snapshot_version", 1),
            ),
        )
        product_row_id = str(cursor.fetchone()[0])
        conn.commit()
        return get_product(tenant_id, product_row_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_product(tenant_id, virtual_product_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {_PRODUCT_COLUMNS}
            FROM procurement.procurement_virtual_products
            WHERE virtual_product_id = ? AND tenant_id = ?
            """,
            (virtual_product_id, tenant_id),
        )
        rows = _rows_to_dicts(cursor)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


def list_products(tenant_id, refresh_id, search, page, page_size):
    where = ["tenant_id = ?", "refresh_id = ?"]
    params = [tenant_id, refresh_id]

    if search:
        where.append("(product_code LIKE ? OR product_name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where_sql = " AND ".join(where)
    offset = (page - 1) * page_size

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COUNT(*) FROM "
            f"procurement.procurement_virtual_products WHERE {where_sql}",
            params,
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT {_PRODUCT_COLUMNS}
            FROM procurement.procurement_virtual_products
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


def remove_product(tenant_id, refresh_id, virtual_product_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            DELETE FROM procurement.procurement_virtual_products
            WHERE virtual_product_id = ? AND refresh_id = ? AND tenant_id = ?
            """,
            (virtual_product_id, refresh_id, tenant_id),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected > 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def bump_products_version(tenant_id, refresh_id):
    """Re-stamp products on metadata refresh (version + updated_at)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE procurement.procurement_virtual_products
            SET snapshot_version = snapshot_version + 1,
                updated_at = GETDATE()
            WHERE refresh_id = ? AND tenant_id = ?
            """,
            (refresh_id, tenant_id),
        )
        affected = cursor.rowcount
        conn.commit()
        return affected
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
