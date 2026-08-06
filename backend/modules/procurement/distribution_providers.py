"""Internal Supplier Stock Distribution — stock source providers.

The distribution pipeline (see ``distribution_service.py``) does not care
where a store's stock came from; it only needs a list of
``{code, name, stock, disc_percent}`` rows for the source store. Two
providers implement that contract so the source can switch from Legacy to
Nexora without touching the pipeline:

- ``LegacyStockProvider``  — runs the master export SQL (unchanged) against
  the legacy OrderNMC database.
- ``NexoraStockProvider``  — reads the same shape from the platform's own
  synced data (sync.Products / sync.ProductTrans / sync.PurchaseTrans) once
  Sync has already landed the source store's latest figures, avoiding a
  second connection to the legacy DB.
"""

from config.database import get_connection, _connection_string
from modules.procurement._dbutil import store_stock_expr

import os

_LEGACY_DB = os.getenv("LEGACY_DB_DATABASE", "OrderNMC")

# Master export query — business logic is fixed, do not change.
_LEGACY_QUERY = """
WITH LatestPT AS (
    SELECT
        pt.*,
        ROW_NUMBER() OVER (
            PARTITION BY pt.ProductCode
            ORDER BY pt.ID DESC
        ) AS rn
    FROM PURCHASETRANS pt
),
TotalStockPerProduct AS (
    SELECT
        b.ProductCode,
        SUM(b.Stock) AS TotalStock
    FROM BATCHES b
    GROUP BY b.ProductCode
)
SELECT
    p.ProductCode,
    p.ProductName,
    tsp.TotalStock AS stock,
    ROUND(
        CASE
            WHEN pt.PurchasePrice > 0
            THEN ((pt.PurchasePrice - pt.ItemCost) * 100.0 / pt.PurchasePrice)
            ELSE 0
        END,
        2
    ) AS ProductDiscPercent
FROM PRODUCTS p
INNER JOIN TotalStockPerProduct tsp
    ON tsp.ProductCode = p.ProductCode
LEFT JOIN LatestPT pt
    ON pt.ProductCode = p.ProductCode
   AND pt.rn = 1
WHERE tsp.TotalStock > 0
ORDER BY p.ProductName
"""


class LegacyStockProvider:
    """Reads the source store's stock straight from its OrderNMC database.

    The platform's only legacy connection is the source ("HO") store's own
    OrderNMC install (see ``supplier_stock_import._legacy_connection``) — the
    master query needs no store filter because that database already holds
    only that store's data.
    """

    name = "legacy"

    def fetch_stock(self, source_store_code):
        import pyodbc
        cs = _connection_string().replace(
            "DATABASE=" + os.getenv("DB_DATABASE", "NEXORA_PLATFORM") + ";",
            "DATABASE=" + _LEGACY_DB + ";",
        )
        conn = pyodbc.connect(cs)
        try:
            cur = conn.cursor()
            cur.execute(_LEGACY_QUERY)
            rows = []
            for r in cur.fetchall():
                rows.append({
                    "code": r.ProductCode,
                    "name": r.ProductName,
                    "stock": float(r.stock or 0),
                    "disc_percent": float(r.ProductDiscPercent or 0),
                })
            return rows
        finally:
            conn.close()


class NexoraStockProvider:
    """Reads the source store's latest synced stock from the platform DB —
    used once Sync has already landed that store's figures, so no second
    connection to the legacy database is needed."""

    name = "nexora"

    def fetch_stock(self, source_store_code):
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT
                    p.ProductCode  AS code,
                    p.ProductName  AS name,
                    {store_stock_expr('p')} AS stock,
                    0 AS disc_percent
                FROM sync.Products p
                JOIN dbo.stores s ON s.store_id = p.store_id
                WHERE s.store_code = ?
                """,
                (source_store_code,),
            )
            rows = []
            for r in cur.fetchall():
                stock = float(r.stock or 0)
                if stock <= 0:
                    continue
                rows.append({
                    "code": r.code,
                    "name": r.name,
                    "stock": stock,
                    "disc_percent": float(r.disc_percent or 0),
                })
            return rows
        finally:
            conn.close()


PROVIDERS = {
    "legacy": LegacyStockProvider(),
    "nexora": NexoraStockProvider(),
}


def get_provider(name):
    provider = PROVIDERS.get(name)
    if not provider:
        raise ValueError(f"Unknown stock provider '{name}' (expected legacy|nexora)")
    return provider
