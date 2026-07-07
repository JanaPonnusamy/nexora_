"""Data access for the Product Intelligence Workspace.

Two responsibilities, cleanly separated:

  * BUILD reads — pull the anchor Refresh + VPL (the source list), discover the
    tenant's ACTIVE stores dynamically, read the Common Product Mapping and each
    store's live stock / suggested quantities / movement metrics. All reads are
    bulk (no N+1); the service does the pure consolidation maths in Python.

  * CACHE reads — the grid, per-product detail, dynamic store metrics, the hover
    payload and the summary are served ENTIRELY from the persisted cache tables
    (product_intelligence_build / _cache / _store). The UI never touches a
    transaction table; the hover endpoint is the only on-demand history read and
    it reuses the proven stock.usp_* stored procedures.

Targets NEXORA_PLATFORM only. Every read/write is tenant-scoped.
"""

from datetime import date, timedelta
from decimal import Decimal

from config.database import get_connection
from modules.procurement._dbutil import (
    as_uid as _as_uid,
    rows_to_dicts as _rows_to_dicts,
    stringify as _stringify,
)


def _floatify(rows):
    for row in rows:
        for key, value in row.items():
            if isinstance(value, Decimal):
                row[key] = float(value)
    return rows


# ==========================================================================
# Dynamic store discovery  (NEVER hardcoded — read from tenant metadata)
# ==========================================================================

def list_active_stores(tenant_id):
    """Active stores for the tenant, ordered by store_code. The grid's store
    columns are generated from exactly this list — nothing is hardcoded."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT store_id, store_code, store_name
            FROM dbo.stores
            WHERE tenant_id = ? AND is_active = 1
            ORDER BY store_code
            """,
            (tenant_id,),
        )
        return [_stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()


def latest_ready_refresh_id(tenant_id, store_id):
    """The most recent generated (Ready) Refresh for a store, or None. Used to
    source each store's own suggested quantities from its immutable VPL."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 refresh_id
            FROM procurement.procurement_refreshes
            WHERE tenant_id = ? AND store_id = ? AND is_deleted = 0
              AND snapshot_status = 'Ready'
            ORDER BY generation_completed_at DESC, created_at DESC
            """,
            (tenant_id, store_id),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None
    finally:
        conn.close()


def latest_ready_refresh_for_tenant(tenant_id):
    """The most recent Ready Refresh for the tenant across any store (the default
    anchor when the caller does not name one)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 refresh_id
            FROM procurement.procurement_refreshes
            WHERE tenant_id = ? AND is_deleted = 0 AND snapshot_status = 'Ready'
            ORDER BY generation_completed_at DESC, created_at DESC
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None
    finally:
        conn.close()


def get_refresh(tenant_id, refresh_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT refresh_id, tenant_id, cycle_id, store_id, snapshot_name,
                   snapshot_status, rolling_days
            FROM procurement.procurement_refreshes
            WHERE refresh_id = ? AND tenant_id = ? AND is_deleted = 0
            """,
            (refresh_id, tenant_id),
        )
        rows = _rows_to_dicts(cur)
        return _stringify(rows[0]) if rows else None
    finally:
        conn.close()


# ==========================================================================
# Build source reads
# ==========================================================================

def anchor_vpl_products(tenant_id, refresh_id):
    """The anchor Refresh's VPL — the SOURCE product list for the workspace.
    Only procurement-eligible products live here (owner-directed VPL scope)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT virtual_product_id, product_id, product_code, product_name,
                   manufacturer_id, mrp, ptr_cost, suggested_qty, current_stock_qty
            FROM procurement.procurement_virtual_products
            WHERE refresh_id = ? AND tenant_id = ?
            ORDER BY product_name
            """,
            (refresh_id, tenant_id),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def load_mappings(tenant_id, store_ids):
    """Common Product Mapping edges (AUTO/APPROVED only) among the active stores.
    ProductCode is NEVER a cross-store key — matches come only from this table."""
    if not store_ids:
        return []
    marks = ", ".join(["?"] * len(store_ids))
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT source_store_id, source_product_code,
                   target_store_id, target_product_code, match_method
            FROM dbo.product_mapping
            WHERE tenant_id = ? AND is_deleted = 0
              AND status IN ('AUTO', 'APPROVED')
              AND source_store_id IN ({marks})
              AND target_store_id IN ({marks})
            """,
            (tenant_id, *store_ids, *store_ids),
        )
        return [_stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()


def store_suggested_map(tenant_id, refresh_id):
    """{product_code: suggested_qty} from a store's latest Ready VPL."""
    if not refresh_id:
        return {}
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT product_code, suggested_qty
            FROM procurement.procurement_virtual_products
            WHERE refresh_id = ? AND tenant_id = ?
            """,
            (refresh_id, tenant_id),
        )
        out = {}
        for code, qty in cur.fetchall():
            if code is not None:
                out[str(code)] = float(qty) if qty is not None else 0.0
        return out
    finally:
        conn.close()


def store_metrics(tenant_id, store_id, rolling_days):
    """Whole-store live metrics keyed by product_code: current stock, average
    daily sale (rolling window), last sale / purchase date, non-moving days and
    the product's commercial context. One bulk read; Python filters to the
    resolved products. Bounded to a 730-day movement lookback."""
    rolling = int(rolling_days or 90) or 90
    cutoff = date.today() - timedelta(days=rolling)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            WITH sales AS (
                SELECT psi.ProductCode,
                       CAST(psi.TransactionDate AS DATE) AS d,
                       ISNULL(psi.Quantity, 0) AS qty
                FROM sync.ProductSaleInformation psi
                WHERE psi.tenant_id = ? AND psi.store_id = ?
                  AND ISNULL(psi.TransactionValidity, 0) = 0
                  AND psi.TransactionDate >= DATEADD(day, -730, GETDATE())
            ),
            sagg AS (
                SELECT ProductCode,
                       MAX(d) AS last_sale_date,
                       SUM(CASE WHEN d >= ? THEN qty ELSE 0 END) AS window_qty
                FROM sales GROUP BY ProductCode
            ),
            pagg AS (
                SELECT ProductCode, MAX(CAST(grndate AS DATE)) AS last_purchase_date
                FROM sync.PurchaseTrans
                WHERE tenant_id = ? AND store_id = ?
                  AND grndate >= DATEADD(day, -730, GETDATE())
                GROUP BY ProductCode
            )
            SELECT
                CAST(p.ProductCode AS VARCHAR(100))       AS product_code,
                p.ProductName                             AS product_name,
                CAST(ISNULL(p.TotalStock, 0) AS DECIMAL(18,3))   AS stock,
                CAST(ISNULL(p.MRP, 0) AS DECIMAL(18,4))          AS mrp,
                CAST(ISNULL(p.PurchasePrice, 0) AS DECIMAL(18,4)) AS ptr,
                CAST(ISNULL(p.Margin, 0) AS DECIMAL(18,4))       AS margin,
                sagg.last_sale_date                       AS last_sale_date,
                pagg.last_purchase_date                   AS last_purchase_date,
                CAST(ISNULL(sagg.window_qty, 0) / ? AS DECIMAL(18,3)) AS avg_sale,
                CASE WHEN sagg.last_sale_date IS NULL THEN NULL
                     ELSE DATEDIFF(day, sagg.last_sale_date, CAST(GETDATE() AS DATE))
                END                                       AS non_moving_days
            FROM sync.Products p
            LEFT JOIN sagg ON sagg.ProductCode = p.ProductCode
            LEFT JOIN pagg ON pagg.ProductCode = p.ProductCode
            WHERE p.tenant_id = ? AND p.store_id = ?
            """,
            (tenant_id, store_id, cutoff, tenant_id, store_id, rolling, tenant_id, store_id),
        )
        out = {}
        for r in _floatify(_rows_to_dicts(cur)):
            code = r.get("product_code")
            if code is not None:
                out[str(code)] = r
        return out
    finally:
        conn.close()


def anchor_last_purchase_rate(tenant_id, store_id, product_codes):
    """{product_code: last purchase price} for the anchor store (detail panel)."""
    if not product_codes:
        return {}
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pt.ProductCode,
                   pt.purchaseprice, pt.mrp, pt.Margin
            FROM sync.PurchaseTrans pt
            INNER JOIN (
                SELECT ProductCode, MAX(grndate) AS mx
                FROM sync.PurchaseTrans
                WHERE tenant_id = ? AND store_id = ?
                GROUP BY ProductCode
            ) last ON last.ProductCode = pt.ProductCode AND last.mx = pt.grndate
            WHERE pt.tenant_id = ? AND pt.store_id = ?
            """,
            (tenant_id, store_id, tenant_id, store_id),
        )
        out = {}
        for r in _floatify(_rows_to_dicts(cur)):
            code = r.get("ProductCode")
            if code is not None and str(code) not in out:
                out[str(code)] = r
        return out
    finally:
        conn.close()


# ==========================================================================
# Build persistence  (one transaction — atomic)
# ==========================================================================

_BUILD_COLS = (
    "build_id", "tenant_id", "refresh_id", "cycle_id", "anchor_store_id",
    "product_count", "store_count", "rolling_days",
    "total_suggest_qty", "total_purchase_qty", "total_transfer_qty", "total_stock_qty",
    "status", "generated_by",
)

_CACHE_COLS = (
    "cache_id", "build_id", "tenant_id", "refresh_id", "vpl_id", "common_product_id",
    "product_code", "product_name", "manufacturer_id",
    "consolidated_suggest_qty", "consolidated_purchase_qty",
    "consolidated_stock_qty", "transfer_qty", "mapped_store_count",
    "mrp", "ptr_cost", "last_purchase_rate", "margin", "offer_text",
)

_STORE_COLS = (
    "cache_store_id", "cache_id", "build_id", "tenant_id", "store_id",
    "product_id", "product_code", "product_name", "match_method",
    "stock_qty", "suggested_qty", "avg_sale",
    "last_sale_date", "last_purchase_date", "non_moving_days",
)


def save_build(header, cache_rows, store_rows):
    """Persist a whole build atomically and retire prior builds for the same
    Refresh (only the newest build per Refresh stays live)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Retire earlier builds for this Refresh so the grid resolves the newest.
        cur.execute(
            """
            UPDATE procurement.product_intelligence_build
            SET is_deleted = 1, deleted_at = GETDATE()
            WHERE tenant_id = ? AND refresh_id = ? AND is_deleted = 0
            """,
            (header["tenant_id"], header["refresh_id"]),
        )

        cur.execute(
            "INSERT INTO procurement.product_intelligence_build ("
            + ", ".join(_BUILD_COLS) + ") VALUES ("
            + ", ".join(["?"] * len(_BUILD_COLS)) + ")",
            tuple(header[c] for c in _BUILD_COLS),
        )

        if cache_rows:
            cur.fast_executemany = True
            cur.executemany(
                "INSERT INTO procurement.product_intelligence_cache ("
                + ", ".join(_CACHE_COLS) + ") VALUES ("
                + ", ".join(["?"] * len(_CACHE_COLS)) + ")",
                [tuple(r[c] for c in _CACHE_COLS) for r in cache_rows],
            )
        if store_rows:
            cur.fast_executemany = True
            cur.executemany(
                "INSERT INTO procurement.product_intelligence_store ("
                + ", ".join(_STORE_COLS) + ") VALUES ("
                + ", ".join(["?"] * len(_STORE_COLS)) + ")",
                [tuple(r[c] for c in _STORE_COLS) for r in store_rows],
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ==========================================================================
# Cache reads  (UI reads ONLY these — never a transaction table)
# ==========================================================================

def latest_build(tenant_id, refresh_id=None):
    where = ["tenant_id = ?", "is_deleted = 0"]
    params = [tenant_id]
    if refresh_id:
        where.append("refresh_id = ?")
        params.append(refresh_id)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT TOP 1 build_id, tenant_id, refresh_id, cycle_id, anchor_store_id,
                   product_count, store_count, rolling_days,
                   total_suggest_qty, total_purchase_qty, total_transfer_qty,
                   total_stock_qty, status, generated_on, generated_by
            FROM procurement.product_intelligence_build
            WHERE {' AND '.join(where)}
            ORDER BY generated_on DESC
            """,
            params,
        )
        rows = _rows_to_dicts(cur)
        return _stringify(_floatify(rows)[0]) if rows else None
    finally:
        conn.close()


def build_stores(build_id):
    """The dynamic store column set for a build (distinct stores that have at
    least one product row), enriched with store code/name for the header."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.store_id, st.store_code, st.store_name,
                   COUNT(*) AS product_count
            FROM procurement.product_intelligence_store s
            LEFT JOIN dbo.stores st ON st.store_id = s.store_id
            WHERE s.build_id = ?
            GROUP BY s.store_id, st.store_code, st.store_name
            ORDER BY st.store_code
            """,
            (build_id,),
        )
        return [_stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()


def grid_rows(build_id):
    """All consolidated product rows for a build (the grid body)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cache_id, common_product_id, product_code, product_name,
                   manufacturer_id,
                   consolidated_suggest_qty, consolidated_purchase_qty,
                   consolidated_stock_qty, transfer_qty, mapped_store_count,
                   mrp, ptr_cost, last_purchase_rate, margin, offer_text
            FROM procurement.product_intelligence_cache
            WHERE build_id = ?
            ORDER BY product_name
            """,
            (build_id,),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def grid_store_cells(build_id):
    """Every per-store cell for a build, keyed by cache_id in the service."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cache_id, store_id, product_code, suggested_qty, stock_qty,
                   avg_sale, last_sale_date, last_purchase_date, non_moving_days,
                   match_method
            FROM procurement.product_intelligence_store
            WHERE build_id = ?
            """,
            (build_id,),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def get_cache(cache_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cache_id, build_id, tenant_id, refresh_id, common_product_id,
                   product_code, product_name, manufacturer_id,
                   consolidated_suggest_qty, consolidated_purchase_qty,
                   consolidated_stock_qty, transfer_qty, mapped_store_count,
                   mrp, ptr_cost, last_purchase_rate, margin, offer_text
            FROM procurement.product_intelligence_cache
            WHERE cache_id = ?
            """,
            (cache_id,),
        )
        rows = _rows_to_dicts(cur)
        return _stringify(_floatify(rows)[0]) if rows else None
    finally:
        conn.close()


def cache_store_rows(cache_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.cache_store_id, s.store_id, st.store_code, st.store_name,
                   s.product_id, s.product_code, s.product_name, s.match_method,
                   s.stock_qty, s.suggested_qty, s.avg_sale,
                   s.last_sale_date, s.last_purchase_date, s.non_moving_days
            FROM procurement.product_intelligence_store s
            LEFT JOIN dbo.stores st ON st.store_id = s.store_id
            WHERE s.cache_id = ?
            ORDER BY st.store_code
            """,
            (cache_id,),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def cache_store_context(cache_id, store_id):
    """The store's ProductCode for one cache product (drives the hover read)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.store_id, s.product_code, s.product_name,
                   s.last_sale_date, s.last_purchase_date, s.non_moving_days,
                   c.tenant_id
            FROM procurement.product_intelligence_store s
            INNER JOIN procurement.product_intelligence_cache c ON c.cache_id = s.cache_id
            WHERE s.cache_id = ? AND s.store_id = ?
            """,
            (cache_id, store_id),
        )
        rows = _rows_to_dicts(cur)
        return _stringify(_floatify(rows)[0]) if rows else None
    finally:
        conn.close()


# ==========================================================================
# Hover history  (on-demand only — reuses the proven stock.usp_* procedures)
# ==========================================================================

def _run_proc(proc, tenant_id, store_id, product_code):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"EXEC {proc} @TenantId = ?, @StoreId = ?, @ProductCode = ?",
            (_as_uid(tenant_id), _as_uid(store_id), int(product_code)),
        )
        if not cur.description:
            return []
        return _floatify(_rows_to_dicts(cur))
    finally:
        conn.close()


def sales_history(tenant_id, store_id, product_code):
    return _run_proc("stock.usp_SalesHistory", tenant_id, store_id, product_code)


def purchase_history(tenant_id, store_id, product_code):
    return _run_proc("stock.usp_PurchaseHistory", tenant_id, store_id, product_code)
