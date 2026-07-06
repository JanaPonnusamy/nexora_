"""Procurement Snapshot Engine — Sprint 3 service layer.

Orchestrates refreshing a VPL by loading raw operational data into its product
rows. Manages the snapshot status lifecycle, runs each refresh inside a single
database transaction, reports progress, and logs outcomes.

It does NOT calculate procurement quantities, assign suppliers, or generate
orders — it only loads and persists raw values via the snapshot repository.
"""

import logging

from fastapi import HTTPException

from config.database import get_connection
from modules.procurement import snapshot_repository as repo
from modules.procurement import vpl_repository as vpl_repo

logger = logging.getLogger("procurement.snapshot")


def _require_vpl(tenant_id, vpl_id):
    vpl = vpl_repo.get_vpl(tenant_id, vpl_id)
    if not vpl:
        raise HTTPException(status_code=404, detail="VPL not found")
    return vpl


def _guard_refreshable(vpl):
    if vpl["snapshot_status"] == "Archived":
        raise HTTPException(
            status_code=409, detail="Archived VPL cannot be snapshotted"
        )


# --------------------------------------------------------------------------
# full / changed refresh
# --------------------------------------------------------------------------

def refresh_vpl(tenant_id, vpl_id, refreshed_by, changed_only=False):
    """Refresh every product (or only changed products) in the VPL.

    Status lifecycle: -> Refreshing -> Ready. Whole operation is one
    transaction; on any error the snapshot is rolled back and the VPL is left
    marked Refreshing for retry, with the error surfaced.
    """
    vpl = _require_vpl(tenant_id, vpl_id)
    _guard_refreshable(vpl)

    product_ids = repo.list_product_ids(tenant_id, vpl_id, changed_only)
    logger.info(
        "Snapshot refresh start vpl=%s tenant=%s products=%d changed_only=%s",
        vpl_id, tenant_id, len(product_ids), changed_only,
    )

    conn = get_connection()
    try:
        repo.set_status_only(conn, tenant_id, vpl_id, "Refreshing")

        # Single-shot source read for the whole VPL; filter to the changed set
        # when requested so we never write rows we didn't intend to refresh.
        source_rows = repo.read_source(conn, tenant_id, vpl_id)
        if changed_only:
            wanted = set(product_ids)
            source_rows = [
                r for r in source_rows if str(r["product_id"]) in wanted
            ]

        updated = repo.bulk_write_snapshot(conn, tenant_id, vpl_id, source_rows)
        repo.stamp_header(conn, tenant_id, vpl_id, "Ready", refreshed_by)

        conn.commit()
        logger.info(
            "Snapshot refresh done vpl=%s updated=%d", vpl_id, updated
        )
    except Exception:
        conn.rollback()
        logger.exception("Snapshot refresh failed vpl=%s", vpl_id)
        raise HTTPException(
            status_code=500, detail="Snapshot refresh failed; rolled back"
        )
    finally:
        conn.close()

    return {
        "vpl_id": vpl_id,
        "status": "Ready",
        "products_refreshed": updated,
        "mode": "changed" if changed_only else "full",
    }


# --------------------------------------------------------------------------
# single-product refresh
# --------------------------------------------------------------------------

def refresh_product(tenant_id, vpl_id, product_id, refreshed_by):
    vpl = _require_vpl(tenant_id, vpl_id)
    _guard_refreshable(vpl)

    if not vpl_repo.product_in_vpl(tenant_id, vpl_id, product_id):
        raise HTTPException(status_code=404, detail="Product not found in VPL")

    conn = get_connection()
    try:
        source_rows = repo.read_source(conn, tenant_id, vpl_id, product_id)
        if not source_rows:
            conn.rollback()
            raise HTTPException(
                status_code=404, detail="No source data for product"
            )
        repo.write_one_snapshot(
            conn, tenant_id, vpl_id, product_id, source_rows[0]
        )
        # touch header audit without forcing whole-VPL Ready
        repo.stamp_header(
            conn, tenant_id, vpl_id, vpl["snapshot_status"], refreshed_by
        )
        conn.commit()
        logger.info(
            "Snapshot product refresh vpl=%s product=%s", vpl_id, product_id
        )
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        logger.exception(
            "Snapshot product refresh failed vpl=%s product=%s",
            vpl_id, product_id,
        )
        raise HTTPException(
            status_code=500, detail="Product snapshot failed; rolled back"
        )
    finally:
        conn.close()

    return {
        "vpl_id": vpl_id,
        "product_id": product_id,
        "status": "refreshed",
    }


# --------------------------------------------------------------------------
# status / progress
# --------------------------------------------------------------------------

def get_status(tenant_id, vpl_id):
    vpl = _require_vpl(tenant_id, vpl_id)
    return {
        "vpl_id": vpl_id,
        "snapshot_status": vpl["snapshot_status"],
        "last_snapshot_on": vpl.get("last_snapshot_on"),
    }


def get_progress(tenant_id, vpl_id):
    vpl = _require_vpl(tenant_id, vpl_id)
    counts = repo.get_progress(tenant_id, vpl_id)
    total = counts["total_products"]
    refreshed = counts["refreshed_products"]
    percent = round((refreshed / total) * 100, 2) if total else 0.0
    return {
        "vpl_id": vpl_id,
        "snapshot_status": vpl["snapshot_status"],
        "total_products": total,
        "refreshed_products": refreshed,
        "pending_products": counts["pending_products"],
        "percent_complete": percent,
    }
