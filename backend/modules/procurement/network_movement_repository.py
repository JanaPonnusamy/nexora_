"""Data access for Network Movement Intelligence.

Reuses the exact batching pattern proven in intelligence_repository.py: one
bulk query per active store (never per product), all cross-store joining done
in Python over already-loaded dicts, one transactional clear+bulk-insert write
(the same shape decision_repository.py uses for the VPL). No new SQL pattern
is invented here.
"""

import os
from decimal import Decimal

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts as _rows_to_dicts, stringify as _stringify
from modules.procurement import intelligence_repository as intel_repo

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")
_DDLS = (
    os.path.join(_SQL_DIR, "0024_product_network_movement.sql"),
    os.path.join(_SQL_DIR, "0025_network_opportunities.sql"),
)
_schema_ready = False


def ensure_schema():
    """Provision procurement.product_network_movement (+ its Network
    Opportunities columns/index) on first use (idempotent) — same self-
    provisioning pattern intelligence_repository.ensure_link_schema() uses, so
    a fresh environment needs no manual migration step."""
    global _schema_ready
    if _schema_ready:
        return
    conn = get_connection()
    try:
        cur = conn.cursor()
        for ddl in _DDLS:
            with open(ddl, "r", encoding="utf-8") as fh:
                script = fh.read()
            for batch in (b.strip() for b in script.split("\nGO")):
                if batch:
                    cur.execute(batch)
        conn.commit()
    finally:
        conn.close()
    _schema_ready = True


def _floatify(rows):
    for row in rows:
        for key, value in row.items():
            if isinstance(value, Decimal):
                row[key] = float(value)
    return rows


# --------------------------------------------------------------------------
# Reused reads — thin pass-throughs to intelligence_repository so there is
# exactly one implementation of "active stores in this tenant", "per-store
# bulk movement metrics" and "mapping edges among these stores".
# --------------------------------------------------------------------------

def list_active_stores(tenant_id):
    return intel_repo.list_active_stores(tenant_id)


def store_movement_metrics(tenant_id, store_id, rolling_days):
    """{product_code: {sales_qty, avg_sale, stock, last_sale_date, ...}} for the
    WHOLE store catalogue (not restricted to that store's VPL) — reuses
    intelligence_repository.store_metrics verbatim; this is precisely the raw
    per-store facts network movement needs and it is already a single bulk
    query per store."""
    return intel_repo.store_metrics(tenant_id, store_id, rolling_days)


def load_mapping_edges(tenant_id, store_ids):
    """AUTO/APPROVED dbo.product_mapping edges among these stores — reuses
    intelligence_repository.load_mappings verbatim (same product-identity
    rules: ProductCode is never a cross-store key on its own)."""
    return intel_repo.load_mappings(tenant_id, store_ids)


def latest_rolling_days(tenant_id, store_ids):
    """The most recently generated Ready Refresh's rolling_days among these
    stores, falling back to 90 — mirrors intelligence_service's own fallback so
    network movement uses the SAME window local movement already uses, not a
    second, independently-chosen window."""
    if not store_ids:
        return 90
    marks = ", ".join(["?"] * len(store_ids))
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT TOP 1 rolling_days
            FROM procurement.procurement_refreshes
            WHERE tenant_id = ? AND is_deleted = 0
              AND snapshot_status = 'Ready'
              AND store_id IN ({marks})
              AND rolling_days IS NOT NULL
            ORDER BY generation_completed_at DESC
            """,
            (tenant_id, *store_ids),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] else 90
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Persistence — clear + bulk insert per tenant (same shape as the VPL write)
# --------------------------------------------------------------------------

INSERT_COLUMNS = (
    "tenant_id", "store_id", "store_product_code", "canonical_product_id",
    "network_movement_class", "network_avg_daily_sales", "network_sales_qty",
    "network_stock_qty", "network_last_sale_date",
    "mapped_store_count", "active_store_count", "fast_store_count",
    "medium_store_count", "slow_store_count", "non_moving_store_count",
    "confidence", "rolling_days",
    "local_sales_qty", "local_avg_daily_sales", "local_stock_qty",
    "local_last_sale_date", "local_movement_class",
)


def replace_all(tenant_id, rows):
    """Atomically replace this tenant's network movement cache — the same
    clear-then-bulk-insert shape decision_repository.py uses for the VPL, so a
    calculation run is either fully applied or not at all."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM procurement.product_network_movement WHERE tenant_id = ?",
            (tenant_id,),
        )
        if rows:
            placeholders = ", ".join(["?"] * len(INSERT_COLUMNS))
            sql = (
                "INSERT INTO procurement.product_network_movement ("
                + ", ".join(INSERT_COLUMNS)
                + ") VALUES (" + placeholders + ")"
            )
            params = [tuple(row[col] for col in INSERT_COLUMNS) for row in rows]
            cur.fast_executemany = True
            cur.executemany(sql, params)
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Reads — the Order Screen's lookup path (grid merge + decision panel)
# --------------------------------------------------------------------------

def get_for_store_products(tenant_id, store_id, product_codes):
    """{product_code: network movement row} for a store, filtered to the
    requested codes. One bulk query per grid page (scoped by the unique index's
    leading columns tenant_id+store_id), never per row and never an IN-list
    sized to the page (the workspace grid allows page_size up to 5000, which
    would risk SQL Server's ~2100-parameter ceiling on an IN-list)."""
    wanted = {str(c) for c in (product_codes or []) if c is not None}
    if not wanted:
        return {}
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT store_product_code, network_movement_class,
                   network_avg_daily_sales, network_sales_qty, network_stock_qty,
                   network_last_sale_date, mapped_store_count, active_store_count,
                   fast_store_count, medium_store_count, slow_store_count,
                   non_moving_store_count, confidence, rolling_days, calculated_at
            FROM procurement.product_network_movement
            WHERE tenant_id = ? AND store_id = ?
            """,
            (tenant_id, store_id),
        )
        out = {}
        for r in _floatify([_stringify(x) for x in _rows_to_dicts(cur)]):
            code = str(r["store_product_code"])
            if code in wanted:
                out[code] = r
        return out
    finally:
        conn.close()


def get_for_store_product(tenant_id, store_id, product_code):
    result = get_for_store_products(tenant_id, store_id, [product_code])
    return result.get(str(product_code))


# --------------------------------------------------------------------------
# Network Opportunities — reads the cache only, never recomputes (Refresh ->
# background network calc -> product_network_movement -> this read path).
# --------------------------------------------------------------------------

_OPPORTUNITIES_WHERE = """
    FROM procurement.product_network_movement nm
    LEFT JOIN sync.Products pr
        ON pr.tenant_id = nm.tenant_id
       AND pr.store_id = nm.store_id
       AND pr.ProductCode = TRY_CAST(nm.store_product_code AS INT)
    WHERE nm.tenant_id = ? AND nm.store_id = ?
      -- local sales are zero right now (the same NONMOVING classification
      -- decision_rules.movement_class already uses; this is a read-only
      -- snapshot copy of that math, not a second definition of it)
      AND nm.local_movement_class = 'NONMOVING'
      -- network movement is a meaningful signal, not just "nonzero somewhere"
      AND nm.network_movement_class IN ('FAST', 'MEDIUM')
      AND nm.network_sales_qty > 0
      -- never surface a product already on this store's Order Screen — that
      -- covers both a VPL-suggested row AND a product a buyer already added
      -- manually (order_items, not the VPL, is the true "already on screen"
      -- set: generate_working_items populates it FROM the VPL, and manual
      -- adds go straight into it without ever gaining a VPL row).
      AND NOT EXISTS (
          SELECT 1 FROM procurement.procurement_order_items oi
          WHERE oi.tenant_id = nm.tenant_id
            AND oi.refresh_id = ?
            AND oi.is_deleted = 0
            AND oi.product_code = nm.store_product_code
      )
"""


def list_opportunities(tenant_id, store_id, refresh_id, page, page_size):
    """Products locally NONMOVING but genuinely moving elsewhere in the
    network, and not already on this store's Order Screen (VPL row or manual
    add). Reads the already-computed cache only — no live cross-store query,
    no recomputation."""
    ensure_schema()
    offset = max(0, (page - 1) * page_size)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT
                nm.store_product_code AS product_code,
                pr.ProductName AS product_name,
                pr.UnitDescription AS unit,
                ISNULL(pr.MRP, 0) AS mrp,
                nm.local_stock_qty AS current_stock,
                nm.local_sales_qty, nm.local_avg_daily_sales, nm.local_movement_class,
                nm.network_movement_class, nm.network_sales_qty, nm.network_avg_daily_sales,
                nm.network_stock_qty, nm.network_last_sale_date,
                nm.mapped_store_count, nm.active_store_count, nm.fast_store_count,
                nm.medium_store_count, nm.confidence, nm.rolling_days, nm.calculated_at
            {_OPPORTUNITIES_WHERE}
            ORDER BY nm.network_sales_qty DESC, nm.store_product_code
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            (tenant_id, store_id, refresh_id, offset, page_size),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def count_opportunities(tenant_id, store_id, refresh_id):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT COUNT(*) {_OPPORTUNITIES_WHERE}",
            (tenant_id, store_id, refresh_id),
        )
        return int(cur.fetchone()[0])
    finally:
        conn.close()
