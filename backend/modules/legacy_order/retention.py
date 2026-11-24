"""180-day retention / trim job for OrderNMC / OrderSMS / OrderSuccess.

Design doc: docs/order-sync-redesign/Order_Sync_Redesign_Plan.md section 3.2.
Full history always stays in NEXORA_PLATFORM.sync.* -- this only trims the
operational central copy so that database stays light. Runs per-tenant via
database.tenant_scoped so it hits whichever of OrderNMC/OrderSMS/OrderSuccess
the active tenant maps to (database.central_connection_string already
resolves that; see database.py's LEGACY_DB_DATABASE_BY_TENANT).

Only genuine append-only transaction LOGS are purged by date. ProductTrans is
deliberately excluded -- it is one running-balance row per product (current
stock/last-bill/last-grn watermarks), not a dated log, so there is nothing in
it that "180 days old" means.
"""
import datetime
import logging

from . import database

logger = logging.getLogger(__name__)

RETENTION_DAYS_DEFAULT = 180

# (table, date_column) for every append-only trans log this job is allowed to
# touch. OrderManagementBackup is intentionally NOT here yet -- repository.
# qty_check_order_history reads TOP 25 per product from it and the SQLite
# cache plan (section 3.3) reads the last 5; a retention cutoff for it needs
# its own row-count check first (see plan doc's open question), not reused
# from this generic job.
PURGEABLE_TABLES = [
    ("SaleInformation", "BillDate"),
    ("PurchaseTrans", "grndate"),
    ("ProductSaleInformation", "TransactionDate"),
]


def _cutoff(retention_days):
    return datetime.date.today() - datetime.timedelta(days=retention_days)


def _configured_tenant_ids():
    """Every tenant this box has a separate central database for (.32:
    SUCCESS+SMS), per database._tenant_database_map(). [None] on a
    single-tenant HO (.73/.80), where there is nothing to loop over --
    database.central_connection_string()'s own LEGACY_DB_DATABASE fallback
    already picks the right (only) database."""
    mapping = database._tenant_database_map()
    return list(mapping.keys()) or [None]


def _count_one(retention_days):
    cutoff = _cutoff(retention_days)
    results = []
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        for table, date_col in PURGEABLE_TABLES:
            try:
                row = cur.execute(
                    f"SELECT COUNT(*), MIN([{date_col}]), MAX([{date_col}]) "
                    f"FROM [{table}] WHERE [{date_col}] < ?",
                    cutoff,
                ).fetchone()
                results.append({
                    "table": table,
                    "date_column": date_col,
                    "rows_older_than_cutoff": int(row[0] or 0),
                    "oldest_date": row[1],
                    "newest_affected_date": row[2],
                })
            except Exception as exc:
                logger.exception("retention count failed for %s", table)
                results.append({"table": table, "date_column": date_col, "error": str(exc)})
    return {"cutoff": cutoff.isoformat(), "retention_days": retention_days, "tables": results}


def _purge_one(retention_days, batch_size):
    cutoff = _cutoff(retention_days)
    results = []
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        for table, date_col in PURGEABLE_TABLES:
            deleted = 0
            try:
                while True:
                    cur.execute(
                        f"DELETE TOP ({batch_size}) FROM [{table}] WHERE [{date_col}] < ?",
                        cutoff,
                    )
                    batch = cur.rowcount
                    conn.commit()
                    deleted += max(batch, 0)
                    if batch < batch_size:
                        break
                results.append({"table": table, "date_column": date_col, "rows_deleted": deleted})
            except Exception as exc:
                conn.rollback()
                logger.exception("retention purge failed for %s", table)
                results.append({"table": table, "date_column": date_col, "rows_deleted": deleted, "error": str(exc)})
    return {"cutoff": cutoff.isoformat(), "retention_days": retention_days, "tables": results}


def count_purgeable_rows(retention_days=RETENTION_DAYS_DEFAULT):
    """Report-only: how many rows in each purgeable table are older than the
    cutoff, for EVERY configured tenant's own central database (.32:
    SUCCESS+SMS each counted separately; .73/.80: one run, no tenant split).
    Deletes nothing. Use this before ever running purge_old_rows for real,
    per the design doc's "report-only first" rule."""
    out = {}
    for tenant_id in _configured_tenant_ids():
        token = database.set_active_tenant(tenant_id)
        try:
            out[tenant_id or "default"] = _count_one(retention_days)
        finally:
            database.reset_active_tenant(token)
    return out


def purge_old_rows(retention_days=RETENTION_DAYS_DEFAULT, batch_size=5000):
    """Deletes rows older than the cutoff, one table at a time, in batches
    (DELETE TOP (n) ... loop) so a single purge run never holds a long lock
    on a busy trans table -- repeated for EVERY configured tenant's own
    central database, same enumeration as count_purgeable_rows. Returns the
    same shape, keyed by tenant_id ("default" on a single-tenant HO), plus a
    rows_deleted count per table."""
    out = {}
    for tenant_id in _configured_tenant_ids():
        token = database.set_active_tenant(tenant_id)
        try:
            out[tenant_id or "default"] = _purge_one(retention_days, batch_size)
        finally:
            database.reset_active_tenant(token)
    return out
