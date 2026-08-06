"""Read-only data access for the Stock Integrity Verification report.

Phase 1 (investigation only): compares SUM(sync.Batches.Stock WHERE Stock > 0)
against sync.Products.TotalStock per (store, ProductCode), entirely within
NEXORA_PLATFORM. No writes.

IMPORTANT: modules/stock_check_report/repository.py already documents a
cross-check finding for this exact pair of columns -- sync.Products.TotalStock
matches sync.ProductTrans.StockInHand (the authoritative store-stock source
per modules/procurement/_dbutil.py:store_stock_expr()), while
SUM(sync.Batches.Stock) is the value that disagrees with both (stale/inflated
batch rows). Do not assume the batch sum is correct without re-verifying
against real data -- see stock_integrity/service.py for the comparison this
module exposes and DO NOT wire up a "repair" path until that assumption is
confirmed against production data.
"""

from pathlib import Path

import pyodbc

from config.database import get_connection
from modules.legacy_order.database import branch_connection_string
from repositories.store_repository import StoreRepository
from services.store_crypto_service import StoreCryptoService

try:
    from store_agent.fernet_key_service import FernetKeyService
except ModuleNotFoundError:
    class FernetKeyService:
        KEY_FILE = Path(__file__).resolve().parents[3] / "store_agent" / "config" / "fernet.key"

        def load_key(self):
            return self.KEY_FILE.read_bytes()

        def key_exists(self):
            return self.KEY_FILE.exists()


def get_mismatches(tenant_id, store_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        params = [tenant_id]
        store_filter = ""
        if store_id:
            store_filter = "AND b.store_id = ?"
            params.append(store_id)

        cursor.execute(
            f"""
            ;WITH BatchAgg AS (
                SELECT b.tenant_id, b.store_id, b.ProductCode,
                       SUM(ISNULL(b.Stock, 0)) AS batch_total
                FROM sync.Batches b
                WHERE b.tenant_id = ?
                  AND ISNULL(b.Stock, 0) > 0
                  {store_filter}
                GROUP BY b.tenant_id, b.store_id, b.ProductCode
            )
            SELECT
                s.store_code                          AS store_code,
                s.store_name                           AS store_name,
                p.store_id                             AS store_id,
                CAST(p.ProductCode AS NVARCHAR(50))    AS product_code,
                p.ProductName                          AS product_name,
                ISNULL(ba.batch_total, 0)              AS store_batch_total,
                ISNULL(p.TotalStock, 0)                AS nexora_total_stock,
                ISNULL(ba.batch_total, 0) - ISNULL(p.TotalStock, 0) AS difference
            FROM sync.Products p
            INNER JOIN dbo.stores s
                    ON s.store_id  = p.store_id
                   AND s.tenant_id = p.tenant_id
            LEFT JOIN BatchAgg ba
                    ON ba.tenant_id   = p.tenant_id
                   AND ba.store_id    = p.store_id
                   AND ba.ProductCode = p.ProductCode
            WHERE p.tenant_id = ?
              {("AND p.store_id = ?" if store_id else "")}
              AND ISNULL(ba.batch_total, 0) <> ISNULL(p.TotalStock, 0)
            ORDER BY s.store_name, p.ProductName
            """,
            tuple(params + [tenant_id] + ([store_id] if store_id else [])),
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        cursor.close()
        conn.close()


def _live_store_config(store_id):
    row = StoreRepository().get_agent_config(store_id)
    if not row:
        raise ValueError("Store configuration not found.")
    if not row[8]:
        raise ValueError("Store is inactive.")

    server_name = row[2]
    database_name = row[3]
    username = row[4]
    password_encrypted = row[5]

    if not server_name or not database_name:
        raise ValueError("Store server/database is not configured.")
    if not username or not password_encrypted:
        raise ValueError("Store DB credentials are not configured.")

    key_service = FernetKeyService()
    if not key_service.key_exists():
        raise ValueError("Store decryption key not found on the server.")

    password = StoreCryptoService.decrypt_password(
        password_encrypted,
        key_service.load_key(),
    )
    return {
        "server_name": server_name,
        "database_name": database_name,
        "username": username,
        "password": password,
    }


def get_live_positive_batches(store_id):
    """Batch rows read live from the store's own SQL Server WHERE Stock > 0.

    Only pulls stocked rows -- far smaller than the full table -- keyed by
    (product_code, batch_code) -> stock.
    """
    cfg = _live_store_config(store_id)
    conn = pyodbc.connect(
        branch_connection_string(
            cfg["server_name"],
            cfg["database_name"],
            cfg["username"],
            cfg["password"],
        ),
        timeout=30,
    )
    try:
        conn.timeout = 300
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT CAST(ProductCode AS NVARCHAR(50)) AS product_code,
                   CAST(BatchCode AS VARCHAR(50))     AS batch_code,
                   Stock                               AS stock
            FROM Batches
            WHERE ISNULL(Stock, 0) > 0
            """
        )
        return {
            (row.product_code, row.batch_code): float(row.stock) for row in cursor.fetchall()
        }
    finally:
        conn.close()


def get_synced_positive_batches(tenant_id, store_id):
    """Batch rows in sync.Batches for this store WHERE Stock > 0, keyed the
    same way as get_live_positive_batches for a direct diff."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT CAST(ProductCode AS NVARCHAR(50)) AS product_code,
                   CAST(BatchCode AS VARCHAR(50))     AS batch_code,
                   Stock                               AS stock
            FROM sync.Batches
            WHERE tenant_id = ? AND store_id = ? AND ISNULL(Stock, 0) > 0
            """,
            (tenant_id, store_id),
        )
        return {
            (row.product_code, row.batch_code): float(row.stock) for row in cursor.fetchall()
        }
    finally:
        cursor.close()
        conn.close()


def diff_positive_batches(live_positive, synced_positive):
    """Union of keys with Stock > 0 on either side, keeping only rows that
    actually disagree. A batch missing from live_positive but present in
    synced_positive means it drained to 0 live and the sync never caught up
    -- exactly the staleness this module was built to find."""
    diffs = []
    for key in set(live_positive) | set(synced_positive):
        live_stock = live_positive.get(key, 0.0)
        synced_stock = synced_positive.get(key, 0.0)
        if live_stock != synced_stock:
            product_code, batch_code = key
            diffs.append((product_code, batch_code, live_stock, synced_stock))
    return diffs


def repair_batch_stock(tenant_id, store_id, diffs, actor_user_id=None):
    """Corrects sync.Batches.Stock for rows that already exist in both live
    and synced data but disagree (as produced by diff_positive_batches).
    Does NOT insert batches missing from sync.Batches entirely -- those need
    a full table resync (many NOT NULL columns this repair doesn't have live
    values for).

    Writes one dbo.stock_integrity_audit row per repaired batch in the same
    transaction as the Stock update.
    """
    conn = get_connection()
    cursor = conn.cursor()
    audit_rows = []
    repaired = 0
    try:
        for product_code, batch_code, live_stock, synced_stock in diffs:
            cursor.execute(
                """
                UPDATE sync.Batches
                SET Stock = ?
                WHERE tenant_id = ? AND store_id = ?
                  AND CAST(ProductCode AS NVARCHAR(50)) = ?
                  AND CAST(BatchCode AS VARCHAR(50)) = ?
                """,
                (live_stock, tenant_id, store_id, product_code, batch_code),
            )
            if cursor.rowcount > 0:
                repaired += cursor.rowcount
                status, detail = "REPAIRED", "Stock corrected from live store DB (stale sync.Batches row)."
            else:
                status, detail = "SKIPPED", "Batch not present in sync.Batches; needs a full table resync, not a Stock patch."
            audit_rows.append(
                (
                    tenant_id, store_id, product_code, batch_code,
                    synced_stock, live_stock, live_stock - synced_stock,
                    status, actor_user_id, detail,
                )
            )

        if audit_rows:
            cursor.executemany(
                """
                INSERT INTO dbo.stock_integrity_audit
                    (tenant_id, store_id, product_code, batch_code,
                     old_stock, new_stock, difference, repair_status,
                     actor_user_id, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                audit_rows,
            )
        conn.commit()
        return {"repaired": repaired}
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


_NAME_BATCH_SIZE = 1000


def get_product_names(tenant_id, store_id, product_codes):
    if not product_codes:
        return {}
    conn = get_connection()
    cursor = conn.cursor()
    try:
        result = {}
        codes = list(product_codes)
        for i in range(0, len(codes), _NAME_BATCH_SIZE):
            batch = codes[i : i + _NAME_BATCH_SIZE]
            placeholders = ",".join("?" * len(batch))
            cursor.execute(
                f"""
                SELECT CAST(ProductCode AS NVARCHAR(50)) AS product_code, ProductName
                FROM sync.Products
                WHERE tenant_id = ? AND store_id = ?
                  AND CAST(ProductCode AS NVARCHAR(50)) IN ({placeholders})
                """,
                tuple([tenant_id, store_id] + batch),
            )
            result.update({row.product_code: row.ProductName for row in cursor.fetchall()})
        return result
    finally:
        cursor.close()
        conn.close()
