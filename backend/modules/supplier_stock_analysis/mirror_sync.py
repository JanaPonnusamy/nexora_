"""product_mapping_mirror sync (PRODMAP-MIRROR-01).

NEXORA_PLATFORM.dbo.product_mapping (APPROVED rows) is the single source of
truth for cross-store product matching, but backfill_store_product_codes()
needs to resolve StoreProductCode on the legacy side (OrderNMC/OrderSMS/
OrderSuccess) without a cross-database join at read time -- see
repository._supplier_stock_source for why that join was too slow to do live.

This module keeps a small local copy, dbo.product_mapping_mirror (see
sql/0002_product_mapping_mirror.sql), inside each tenant's own central
database, refreshed two ways:
  - a background tick every MIRROR_SYNC_TICK_SECONDS (same pattern as
    modules/sync/scheduler_service.py), covering all tenants in turn;
  - sync_tenant_now(tenant_id), called right after a mapping is approved
    (see product_mapping/service.approve_mapping) so a manual match is
    usable immediately instead of waiting for the next tick.

Same-instance by default (NEXORA_PLATFORM and OrderNMC normally share one
SQL Server -- see legacy_order/database.py), so the refresh itself is a
local INSERT, not network replication.
"""
import logging
import os
import threading

from config.database import get_connection
from modules.legacy_order import database as legacy_database

logger = logging.getLogger("supplier_stock_analysis.mirror_sync")

TICK_SECONDS = int(os.getenv("PRODUCT_MAPPING_MIRROR_TICK_SECONDS", "900"))

_stop_event = threading.Event()
_thread = None
_last_tick = {"at": None, "summary": None, "error": None}


def get_status():
    return {
        "tick_seconds": TICK_SECONDS,
        "last_tick_at": _last_tick["at"].isoformat() if _last_tick["at"] else None,
        "last_tick_summary": _last_tick["summary"],
        "last_tick_error": _last_tick["error"],
    }


def _active_tenant_ids():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT tenant_id FROM dbo.tenants WHERE is_active = 1")
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def _approved_mappings(tenant_id):
    """store_code/source_product_code/target_product_code triples for every
    live APPROVED mapping of this tenant, store_id resolved to store_code via
    dbo.stores (the mirror join keys on StoreName, same as SupplierStock).

    One (source store, source_product_code) can legitimately map to several
    DIFFERENT target stores (that's the point of cross-store mapping), but
    the mirror's PK is (store_name, source_product_code) -- it exists only
    to answer "what is this store's product resolved to," one answer per
    product, not to carry the full cross-matrix. Highest-confidence row per
    key wins; ties broken by most recently updated."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT store_code, source_product_code, target_product_code FROM (
                SELECT st.store_code, pm.source_product_code, pm.target_product_code,
                       ROW_NUMBER() OVER (
                           PARTITION BY st.store_code, pm.source_product_code
                           ORDER BY pm.confidence DESC, pm.updated_at DESC
                       ) AS rn
                FROM dbo.product_mapping pm
                JOIN dbo.stores st ON st.store_id = pm.source_store_id
                WHERE pm.tenant_id = ? AND pm.is_deleted = 0 AND pm.status = 'APPROVED'
                  AND pm.target_product_code IS NOT NULL
            ) ranked
            WHERE rn = 1
            """,
            (tenant_id,),
        )
        return cur.fetchall()
    finally:
        conn.close()


def sync_tenant_now(tenant_id):
    """Refresh dbo.product_mapping_mirror inside this tenant's own central
    database from its current APPROVED mappings. Returns rows written, or
    None if the tenant's legacy DB is unreachable (best-effort: a stale
    mirror is far better than breaking the caller)."""
    rows = _approved_mappings(tenant_id)
    token = legacy_database.set_active_tenant(tenant_id)
    try:
        conn = legacy_database.get_central_connection(timeout=10)
    except Exception:
        logger.warning("mirror sync: tenant %s legacy DB unreachable, skipped", tenant_id)
        legacy_database.reset_active_tenant(token)
        return None
    try:
        cur = conn.cursor()
        cur.execute(
            "IF OBJECT_ID('dbo.product_mapping_mirror', 'U') IS NULL "
            "RAISERROR('product_mapping_mirror missing -- run sql/0002', 16, 1)"
        )
        cur.execute("TRUNCATE TABLE dbo.product_mapping_mirror")
        # Multi-row INSERT in chunks, not executemany() -- one round trip per
        # chunk instead of one per row. At tens of thousands of rows over a
        # remote legacy-DB link (the normal case: OrderSMS/OrderSuccess are on
        # .32, this backend can run anywhere), per-row executemany() took
        # 6-7 minutes for ~83K rows, which can't keep up with a 15-minute
        # tick. 500 rows/statement keeps well under SQL Server's 2100
        # parameter limit (500*3 = 1500).
        CHUNK = 500
        values = [(store_code, source_code, target_code) for store_code, source_code, target_code in rows]
        for i in range(0, len(values), CHUNK):
            batch = values[i:i + CHUNK]
            placeholders = ", ".join(["(?, ?, ?)"] * len(batch))
            params = [v for row in batch for v in row]
            cur.execute(
                f"INSERT INTO dbo.product_mapping_mirror "
                f"(store_name, source_product_code, target_product_code) VALUES {placeholders}",
                params,
            )
        conn.commit()
        return len(rows)
    finally:
        conn.close()
        legacy_database.reset_active_tenant(token)


def run_tick():
    summary = {}
    try:
        for tenant_id in _active_tenant_ids():
            try:
                written = sync_tenant_now(tenant_id)
                summary[str(tenant_id)] = written
            except Exception as ex:
                logger.exception("mirror sync failed for tenant %s", tenant_id)
                summary[str(tenant_id)] = f"error: {ex}"
        import datetime

        _last_tick["at"] = datetime.datetime.now()
        _last_tick["summary"] = summary
        _last_tick["error"] = None
    except Exception as ex:
        import datetime

        _last_tick["at"] = datetime.datetime.now()
        _last_tick["error"] = str(ex)
    return summary


def _loop():
    while not _stop_event.wait(TICK_SECONDS):
        run_tick()


def start_background_loop():
    """Idempotent: calling this more than once never spawns a second thread."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return _thread
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="nexora-product-mapping-mirror", daemon=True)
    _thread.start()
    return _thread


def stop_background_loop():
    _stop_event.set()
