"""Supplier Export service (Sprint 2, Modules 6 & 7).

Stamps a new export batch onto the draft assignments of a Refresh (all, or a
selected subset). Each distinct supplier in the batch gets its own split number;
each assignment gets a unique export UID. Validation (Module 7): nothing to
export -> 400; assignments without a supplier or with qty <= 0 are excluded at
the SQL level. Multiple exports are allowed. History is read from the records.
"""

import uuid

from fastapi import HTTPException

from config.database import get_connection
from modules.procurement import export_repository as repo

import logging

logger = logging.getLogger("procurement.export")


def export_refresh(tenant_id, refresh_id, exported_by, assignment_ids=None, supplier_code=None):
    if not exported_by:
        raise HTTPException(
            status_code=403, detail="exported_by (user) is required to export"
        )

    conn = get_connection()
    try:
        rows = repo.exportable_assignments(conn, tenant_id, refresh_id, assignment_ids, supplier_code)
        if not rows:
            raise HTTPException(
                status_code=400, detail="No exportable assignments for this Refresh"
            )

        batch_no = "EXP-" + uuid.uuid4().hex[:12].upper()
        # One split number per distinct supplier within the batch.
        split_of = {}
        for row in rows:
            supplier = row["supplier_code"]
            if supplier not in split_of:
                split_of[supplier] = len(split_of) + 1

        exported = 0
        for row in rows:
            repo.mark_exported(
                conn, tenant_id, row["assignment_id"], batch_no,
                split_of[row["supplier_code"]], uuid.uuid4().hex, exported_by,
            )
            exported += 1
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    logger.info("Export tenant=%s refresh=%s batch=%s lines=%s suppliers=%s by=%s",
                tenant_id, refresh_id, batch_no, exported, len(split_of), exported_by)
    return {
        "export_batch_number": batch_no,
        "exported_count": exported,
        "supplier_count": len(split_of),
        "splits": len(split_of),
    }


def history(tenant_id, refresh_id):
    return {"batches": repo.export_history(tenant_id, refresh_id)}


def batch_detail(tenant_id, batch_no):
    return {"batch": batch_no, "lines": repo.export_batch_detail(tenant_id, batch_no)}
