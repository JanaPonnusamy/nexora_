"""Data access for the Sale Analysis module.

Two kinds of data live here:

* Group definitions — persisted in NEXORA_PLATFORM under ``dbo`` (tenant-scoped;
  a group is a named list of product codes, reusable across the tenant's stores).
  Tables are created on demand (``ensure_schema``, grid_settings style).
* Report metrics — read-only aggregates over the synced ``sync.*`` tables for a
  single store: current stock, sales in a window, and the cost columns.

"Current store stock" follows the platform-wide rule (latest month of
``sync.ProductTrans.StockInHand``, falling back to ``Products.TotalStock``) — the
same expression the Procurement module uses, so the numbers reconcile.
"""

from __future__ import annotations

import uuid

from config.database import get_connection
from modules.procurement._dbutil import store_stock_expr

_SCHEMA_READY = False


def _run(cursor):
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, r)) for r in cursor.fetchall()]


def ensure_schema(cursor):
    """Idempotent — safe to call before every query."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    cursor.execute(
        """
        IF OBJECT_ID('dbo.sale_analysis_group', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.sale_analysis_group (
                group_id    UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_sag_id DEFAULT NEWID(),
                tenant_id   UNIQUEIDENTIFIER NOT NULL,
                group_name  NVARCHAR(200)    NOT NULL,
                created_by  UNIQUEIDENTIFIER NULL,
                created_at  DATETIME2        NOT NULL CONSTRAINT DF_sag_created DEFAULT SYSUTCDATETIME(),
                updated_at  DATETIME2        NOT NULL CONSTRAINT DF_sag_updated DEFAULT SYSUTCDATETIME(),
                CONSTRAINT PK_sale_analysis_group PRIMARY KEY (group_id)
            );
            CREATE INDEX IX_sale_analysis_group_tenant ON dbo.sale_analysis_group (tenant_id);
        END
        -- Group items are keyed by product NAME, not code: product codes differ
        -- from store to store, so a code-based group is meaningless across
        -- stores. A name-based group ("FRIENDS") resolves to each store's own
        -- matching products at report time. Migrate a legacy code-based item
        -- table (safe: recreated only when the product_name column is absent).
        IF OBJECT_ID('dbo.sale_analysis_group_item', 'U') IS NOT NULL
           AND COL_LENGTH('dbo.sale_analysis_group_item', 'product_name') IS NULL
            DROP TABLE dbo.sale_analysis_group_item;
        IF OBJECT_ID('dbo.sale_analysis_group_item', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.sale_analysis_group_item (
                group_id     UNIQUEIDENTIFIER NOT NULL,
                product_name NVARCHAR(300)    NOT NULL,
                CONSTRAINT PK_sale_analysis_group_item PRIMARY KEY (group_id, product_name)
            );
        END
        """
    )
    _SCHEMA_READY = True


def _as_uid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Lookups — product & supplier search (for building a group)
# ---------------------------------------------------------------------------

def search_products(tenant_id, store_id, query, supplier_code=None, limit=50):
    """Products matching a name/code substring (+ optional supplier), with the
    product's current store stock so the builder can preview it."""
    q = (query or "").strip()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        where = ["p.tenant_id = ?", "p.store_id = ?", "ISNULL(p.isActive, 1) = 1"]
        params = [tenant_id, store_id]
        # Match by product NAME only — product codes differ from store to store,
        # so code matching is meaningless for cross-store groups (req).
        where.append("( ? = '' OR p.ProductName LIKE '%' + ? + '%' )")
        params += [q, q]
        if supplier_code:
            where.append("CAST(p.SupplierCode AS VARCHAR(50)) = ?")
            params.append(str(supplier_code))
        cursor.execute(
            f"""
            SELECT TOP ({int(limit)})
                CAST(p.ProductCode AS VARCHAR(50)) AS product_code,
                RTRIM(p.ProductName)               AS product_name,
                CAST(p.SupplierCode AS VARCHAR(50)) AS supplier_code,
                RTRIM(s.suppliername)              AS supplier_name,
                {store_stock_expr("p")}            AS current_stock,
                ISNULL(p.MRP, 0)                   AS mrp
            FROM sync.Products p
            LEFT JOIN sync.Suppliers s
                ON s.tenant_id = p.tenant_id AND s.store_id = p.store_id
               AND s.suppliercode = p.SupplierCode
            WHERE {' AND '.join(where)}
            ORDER BY p.ProductName
            """,
            tuple(params),
        )
        return _run(cursor)
    finally:
        conn.close()


def search_suppliers(tenant_id, store_id, query, limit=30):
    q = (query or "").strip()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT TOP ({int(limit)})
                CAST(suppliercode AS VARCHAR(50)) AS supplier_code,
                RTRIM(suppliername)               AS supplier_name
            FROM sync.Suppliers
            WHERE tenant_id = ? AND store_id = ?
              AND ( ? = '' OR suppliername LIKE '%' + ? + '%' )
            ORDER BY suppliername
            """,
            (tenant_id, store_id, q, q),
        )
        return _run(cursor)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Group CRUD (NEXORA_PLATFORM / dbo)
# ---------------------------------------------------------------------------

def list_groups(tenant_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_schema(cursor)
        cursor.execute(
            """
            SELECT g.group_id, g.group_name, g.updated_at,
                   (SELECT COUNT(*) FROM dbo.sale_analysis_group_item i
                    WHERE i.group_id = g.group_id) AS item_count
            FROM dbo.sale_analysis_group g
            WHERE g.tenant_id = ?
            ORDER BY g.group_name
            """,
            (tenant_id,),
        )
        rows = _run(cursor)
        for r in rows:
            r["group_id"] = str(r["group_id"])
            r["updated_at"] = r["updated_at"].isoformat() if r.get("updated_at") else None
        return rows
    finally:
        conn.close()


def get_group(tenant_id, group_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_schema(cursor)
        cursor.execute(
            """
            SELECT group_id, group_name, updated_at
            FROM dbo.sale_analysis_group
            WHERE tenant_id = ? AND group_id = ?
            """,
            (tenant_id, group_id),
        )
        head = _run(cursor)
        if not head:
            return None
        cursor.execute(
            "SELECT product_name FROM dbo.sale_analysis_group_item WHERE group_id = ? ORDER BY product_name",
            (group_id,),
        )
        names = [str(r[0]) for r in cursor.fetchall()]
        g = head[0]
        return {
            "group_id": str(g["group_id"]),
            "group_name": g["group_name"],
            "updated_at": g["updated_at"].isoformat() if g.get("updated_at") else None,
            "item_count": len(names),
            "product_names": names,
        }
    finally:
        conn.close()


def save_group(tenant_id, group_name, product_names, created_by=None, group_id=None):
    """Create (group_id is None) or replace an existing group's items. Items are
    product NAMES (case-preserved), so the group resolves per store at report."""
    names = sorted({str(c).strip() for c in (product_names or []) if str(c).strip()})
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_schema(cursor)
        if group_id:
            cursor.execute(
                """
                UPDATE dbo.sale_analysis_group
                SET group_name = ?, updated_at = SYSUTCDATETIME()
                WHERE tenant_id = ? AND group_id = ?
                """,
                (group_name, tenant_id, group_id),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return None
            cursor.execute("DELETE FROM dbo.sale_analysis_group_item WHERE group_id = ?", (group_id,))
            gid = str(group_id)
        else:
            gid = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO dbo.sale_analysis_group (group_id, tenant_id, group_name, created_by)
                VALUES (?, ?, ?, ?)
                """,
                (gid, tenant_id, group_name, _as_uid(created_by)),
            )
        for name in names:
            cursor.execute(
                "INSERT INTO dbo.sale_analysis_group_item (group_id, product_name) VALUES (?, ?)",
                (gid, name),
            )
        conn.commit()
        return gid
    finally:
        conn.close()


def delete_group(tenant_id, group_id):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        ensure_schema(cursor)
        cursor.execute(
            "DELETE FROM dbo.sale_analysis_group WHERE tenant_id = ? AND group_id = ?",
            (tenant_id, group_id),
        )
        deleted = cursor.rowcount
        cursor.execute("DELETE FROM dbo.sale_analysis_group_item WHERE group_id = ?", (group_id,))
        conn.commit()
        return deleted > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Report metrics — per-product stock vs sales for a set of product codes
# ---------------------------------------------------------------------------

def product_metrics(tenant_id, store_id, product_names, from_date, to_date):
    """Raw per-product numbers for the given product NAMES in the store/window.

    Matching is by product name (not code) so one saved group resolves to each
    store's own products. Returns rows with: ProductCode, ProductName,
    SupplierName, Stock, PTR, SaleUnit, SaleQty, SalesCost. The derived columns
    (avg daily sale, cover days, excess, stock/excess cost) are computed in the
    service so the window/target arithmetic lives in one place.
    """
    names = [str(c).strip() for c in (product_names or []) if str(c).strip()]
    if not names:
        return []
    conn = get_connection()
    try:
        cursor = conn.cursor()
        # Chunk the IN list to stay well under SQL Server's parameter ceiling.
        out = []
        CHUNK = 500
        for i in range(0, len(names), CHUNK):
            batch = names[i:i + CHUNK]
            placeholders = ",".join("?" for _ in batch)
            sql = f"""
                SELECT
                    CAST(p.ProductCode AS VARCHAR(50)) AS ProductCode,
                    RTRIM(p.ProductName)               AS ProductName,
                    RTRIM(COALESCE(s.suppliername,
                        CAST(p.SupplierCode AS VARCHAR(50)))) AS SupplierName,
                    {store_stock_expr("p")}            AS Stock,
                    ISNULL(p.PurchasePrice, 0)         AS PTR,
                    ISNULL(NULLIF(p.SaleUnit, 0), 1)   AS SaleUnit,
                    ISNULL(sa.SaleQty, 0)              AS SaleQty,
                    ISNULL(sa.SalesCost, 0)            AS SalesCost
                FROM sync.Products p
                LEFT JOIN sync.Suppliers s
                    ON s.tenant_id = p.tenant_id AND s.store_id = p.store_id
                   AND s.suppliercode = p.SupplierCode
                LEFT JOIN (
                    SELECT ProductCode,
                           SUM(Quantity)    AS SaleQty,
                           SUM(CostOfSales) AS SalesCost
                    FROM sync.ProductSaleInformation
                    WHERE tenant_id = ? AND store_id = ?
                      AND CAST(TransactionDate AS DATE) BETWEEN ? AND ?
                      AND TransactionValidity = 0
                      AND seriesname NOT IN ('n', 'sa', 'er')
                    GROUP BY ProductCode
                ) sa ON sa.ProductCode = p.ProductCode
                WHERE p.tenant_id = ? AND p.store_id = ?
                  AND ISNULL(p.isActive, 1) = 1
                  AND RTRIM(p.ProductName) IN ({placeholders})
                ORDER BY p.ProductName
            """
            params = [tenant_id, store_id, from_date, to_date, tenant_id, store_id, *batch]
            cursor.execute(sql, tuple(params))
            out.extend(_run(cursor))
        return out
    finally:
        conn.close()
