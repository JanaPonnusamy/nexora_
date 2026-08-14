"""Internal Supplier Stock Distribution — stock source providers.

The distribution pipeline (see ``distribution_service.py``) does not care
where a store's stock came from; it only needs a list of
``{code, name, stock, disc_percent, rack}`` rows for the source store. Two
providers implement that contract so the source can switch from Legacy to
Nexora without touching the pipeline:

- ``LegacyStockProvider``  — delegates to
  ``modules.legacy_order.repository.branch_stock()``, the already-proven
  legacy port that connects to the SOURCE STORE'S OWN branch SQL Server
  (server/database/credentials looked up per-store from the central
  OrderNMC.dbo.Stores table) and runs the master PRODUCTS/BATCHES/
  PURCHASETRANS export query there. IMPORTANT: this module used to run that
  same query directly against the *central* OrderNMC database instead —
  which has its OWN Products/Batches tables (a 220k-row combined mirror
  across every store, not NMW's ~1.2k) — silently returning the wrong
  store's/every store's stock and no rack data. Delegating to
  ``branch_stock`` (which legacy_order already gets right, rack included)
  fixes that at the source instead of maintaining a second, divergent copy
  of the same query.
- ``NexoraStockProvider``  — reads the same shape from the platform's own
  synced data (sync.Products / sync.ProductTrans / sync.PurchaseTrans) once
  Sync has already landed the source store's latest figures, avoiding a
  second connection to the legacy DB.
"""

from config.database import get_connection
from modules.procurement._dbutil import store_stock_expr


class LegacyStockProvider:
    """Reads the source store's stock straight from ITS OWN branch database
    — never the central OrderNMC mirror — via the already-proven legacy port
    (modules.legacy_order.repository), rack/SubLocation included."""

    name = "legacy"

    def fetch_stock(self, source_store_code):
        from modules.legacy_order import repository as legacy_repo

        store = legacy_repo.get_store(source_store_code)
        if not store:
            raise ValueError(
                f"'{source_store_code}' is not a configured branch in the legacy "
                "OrderNMC console (dbo.Stores) — cannot read its live stock."
            )
        return [
            {
                "code": r["code"],
                "name": r["name"],
                "stock": r["stock"],
                "disc_percent": r["disc_percent"],
                "rack": r["rack"],
            }
            for r in legacy_repo.branch_stock(store)
        ]


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
                    p.SubLocation  AS rack,
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
                    "rack": (r.rack or "").strip() or None,
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
