"""Data access for the Product Intelligence Workspace (network-wide).

Two responsibilities, cleanly separated:

  * BUILD reads — pull EVERY participating store's Refresh + VPL (the union of
    those VPLs is the product universe), read the Common Product Mapping (whose
    deterministic edges are derived from sync.SupplierProductMatch), the supplier
    identity of each product, and each store's live stock / sales / purchase
    metrics. All reads are bulk (no N+1); the service does the pure consolidation
    maths in Python.

  * CACHE reads — the grid, per-product detail, per-store metrics, the per-store
    history panel and the summary are served ENTIRELY from the persisted cache
    tables (product_intelligence_build / _build_store / _cache / _store). The UI
    never touches a transaction table; the history endpoint is the only on-demand
    read and it reuses the proven stock.usp_* stored procedures.

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


def latest_ready_refresh(tenant_id, store_id):
    """The most recent generated (Ready) Refresh for a store — the store VPL the
    build consumes. None when the store has never been refreshed."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP 1 refresh_id, cycle_id, store_id, rolling_days,
                   generated_product_count, generation_completed_at
            FROM procurement.procurement_refreshes
            WHERE tenant_id = ? AND store_id = ? AND is_deleted = 0
              AND snapshot_status IN ('Ready', 'Archived')
            ORDER BY generation_completed_at DESC, created_at DESC
            """,
            (tenant_id, store_id),
        )
        rows = _rows_to_dicts(cur)
        return _stringify(rows[0]) if rows else None
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

def store_vpl_products(tenant_id, refresh_id):
    """ONE store's VPL — its own procurement demand, calculated by the existing
    Decision Engine from that store's own sales / stock / purchase history.

    The union of these lists across stores is the workspace's product universe:
    a product NMW never sold is absent from NMW's VPL but present in NMC's, and
    the warehouse still has to buy it. Only procurement-eligible products live in
    a VPL (owner-directed VPL scope)."""
    if not refresh_id:
        return []
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT virtual_product_id, product_id, product_code, product_name,
                   manufacturer_id, mrp, ptr_cost,
                   suggested_qty, current_stock_qty, avg_daily_sales,
                   window_sales_qty, days_cover, movement_class, stock_status
            FROM procurement.procurement_virtual_products
            WHERE refresh_id = ? AND tenant_id = ?
            """,
            (refresh_id, tenant_id),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def load_mappings(tenant_id, store_ids):
    """Common Product Mapping edges (AUTO/APPROVED) among the participating
    stores. These edges are how — and the ONLY way — two stores' products are
    known to be the same thing: the deterministic ones are derived by joining
    sync.SupplierProductMatch on (SupplierCode, SupplierProductCode), never on
    equal ProductCode. Carries confidence + method so the grid can show how much
    to trust each consolidated row."""
    if not store_ids:
        return []
    marks = ", ".join(["?"] * len(store_ids))
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT source_store_id, source_product_code,
                   target_store_id, target_product_code,
                   match_method, confidence
            FROM dbo.product_mapping
            WHERE tenant_id = ? AND is_deleted = 0
              AND status IN ('AUTO', 'APPROVED')
              AND target_product_code IS NOT NULL
              AND source_store_id IN ({marks})
              AND target_store_id IN ({marks})
            """,
            (tenant_id, *store_ids, *store_ids),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def load_supplier_identity(tenant_id, store_ids):
    """{(store_id, product_code): {supplier_code, supplier_product_code,
    supplier_product_name}} from sync.SupplierProductMatch — the canonical
    supplier line behind a store's ProductCode. Gives each consolidated row its
    "Supplier Product" identity. Empty when the table is not provisioned."""
    if not store_ids:
        return {}
    marks = ", ".join(["?"] * len(store_ids))
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT OBJECT_ID('sync.SupplierProductMatch')")
        if cur.fetchone()[0] is None:
            return {}
        cur.execute(
            f"""
            SELECT store_id,
                   CAST(ProductCode AS VARCHAR(100))         AS product_code,
                   CAST(SupplierCode AS VARCHAR(50))         AS supplier_code,
                   CAST(SupplierProductCode AS VARCHAR(100)) AS supplier_product_code,
                   SupplierProductName                       AS supplier_product_name,
                   lastmodifieddate
            FROM sync.SupplierProductMatch
            WHERE tenant_id = ? AND store_id IN ({marks})
              AND ProductCode IS NOT NULL
              AND ISNULL(isactive, 1) = 1
            ORDER BY lastmodifieddate DESC
            """,
            (tenant_id, *store_ids),
        )
        out = {}
        for r in [_stringify(x) for x in _rows_to_dicts(cur)]:
            key = (r["store_id"], str(r["product_code"]))
            # ORDER BY puts the most recently modified link first — keep it.
            if key not in out:
                out[key] = {
                    "supplier_code": r.get("supplier_code"),
                    "supplier_product_code": r.get("supplier_product_code"),
                    "supplier_product_name": r.get("supplier_product_name"),
                }
        return out
    finally:
        conn.close()


def store_metrics(tenant_id, store_id, rolling_days):
    """Whole-store live metrics keyed by product_code: current stock, rolling
    window sales qty + average daily sale, rolling window purchase qty, last sale
    / purchase date, non-moving days and commercial context.

    One bulk read per store; Python filters to the resolved products. This is what
    gives a store PRESENCE in a consolidated row even when the product is not in
    that store's VPL (it holds stock, but needs nothing) — bounded to a 730-day
    lookback."""
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
                SELECT ProductCode,
                       MAX(CAST(grndate AS DATE)) AS last_purchase_date,
                       SUM(CASE WHEN CAST(grndate AS DATE) >= ?
                                THEN ISNULL(stockreceived, 0) + ISNULL(FreeQty, 0)
                                ELSE 0 END) AS window_purchase_qty
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
                CAST(ISNULL(sagg.window_qty, 0) AS DECIMAL(18,3))          AS sales_qty,
                CAST(ISNULL(pagg.window_purchase_qty, 0) AS DECIMAL(18,3)) AS purchase_qty,
                CAST(ISNULL(sagg.window_qty, 0) / ? AS DECIMAL(18,3))      AS avg_sale,
                CASE WHEN sagg.last_sale_date IS NULL THEN NULL
                     ELSE DATEDIFF(day, sagg.last_sale_date, CAST(GETDATE() AS DATE))
                END                                       AS non_moving_days
            FROM sync.Products p
            LEFT JOIN sagg ON sagg.ProductCode = p.ProductCode
            LEFT JOIN pagg ON pagg.ProductCode = p.ProductCode
            WHERE p.tenant_id = ? AND p.store_id = ?
            """,
            (tenant_id, store_id, cutoff, cutoff, tenant_id, store_id,
             rolling, tenant_id, store_id),
        )
        out = {}
        for r in _floatify(_rows_to_dicts(cur)):
            code = r.get("product_code")
            if code is not None:
                out[str(code)] = r
        return out
    finally:
        conn.close()


def last_purchase_rates(tenant_id, store_id):
    """{product_code: last purchase price/mrp/margin} for one store (the warehouse
    supplies the commercial context the Purchase Manager reads)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT pt.ProductCode, pt.purchaseprice, pt.mrp, pt.Margin
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
    "warehouse_store_id",
    "product_count", "store_count", "rolling_days",
    "total_need_qty", "total_suggest_qty", "total_purchase_qty",
    "total_transfer_qty", "total_stock_qty",
    "status", "generated_by",
)

_BUILD_STORE_COLS = (
    "build_store_id", "build_id", "tenant_id", "store_id", "refresh_id",
    "is_warehouse", "vpl_product_count", "vpl_generated_on",
)

_CACHE_COLS = (
    "cache_id", "build_id", "tenant_id", "refresh_id", "vpl_id", "common_product_id",
    "product_code", "product_name", "manufacturer_id",
    "supplier_code", "supplier_product_code", "supplier_product_name",
    "consolidated_suggest_qty", "consolidated_purchase_qty",
    "consolidated_stock_qty", "transfer_qty", "mapped_store_count",
    "warehouse_stock_qty", "warehouse_product_code", "warehouse_suggest_qty",
    "total_sales_qty", "total_purchase_qty",
    "priority", "priority_rank", "stockout_store_count",
    "confidence", "match_method",
    "mrp", "ptr_cost", "last_purchase_rate", "margin", "offer_text",
)

_STORE_COLS = (
    "cache_store_id", "cache_id", "build_id", "tenant_id", "store_id",
    "product_id", "product_code", "product_name", "match_method",
    "stock_qty", "suggested_qty", "avg_sale", "sales_qty", "purchase_qty",
    "days_cover", "in_vpl", "is_warehouse", "refresh_id",
    "last_sale_date", "last_purchase_date", "non_moving_days",
)


def save_build(header, build_stores, cache_rows, store_rows):
    """Persist a whole build atomically and retire prior builds for the same
    tenant + warehouse (only the newest build stays live)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Retire earlier builds for this warehouse so the grid resolves the newest.
        cur.execute(
            """
            UPDATE procurement.product_intelligence_build
            SET is_deleted = 1, deleted_at = GETDATE()
            WHERE tenant_id = ? AND is_deleted = 0
              AND (warehouse_store_id = ? OR warehouse_store_id IS NULL)
            """,
            (header["tenant_id"], header["warehouse_store_id"]),
        )

        cur.execute(
            "INSERT INTO procurement.product_intelligence_build ("
            + ", ".join(_BUILD_COLS) + ") VALUES ("
            + ", ".join(["?"] * len(_BUILD_COLS)) + ")",
            tuple(header[c] for c in _BUILD_COLS),
        )

        if build_stores:
            cur.executemany(
                "INSERT INTO procurement.product_intelligence_build_store ("
                + ", ".join(_BUILD_STORE_COLS) + ") VALUES ("
                + ", ".join(["?"] * len(_BUILD_STORE_COLS)) + ")",
                [tuple(r[c] for c in _BUILD_STORE_COLS) for r in build_stores],
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

def latest_build(tenant_id, build_id=None, warehouse_store_id=None):
    where = ["tenant_id = ?", "is_deleted = 0"]
    params = [tenant_id]
    if build_id:
        where.append("build_id = ?")
        params.append(build_id)
    if warehouse_store_id:
        where.append("warehouse_store_id = ?")
        params.append(warehouse_store_id)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT TOP 1 build_id, tenant_id, refresh_id, cycle_id, anchor_store_id,
                   warehouse_store_id, product_count, store_count, rolling_days,
                   total_need_qty, total_suggest_qty, total_purchase_qty,
                   total_transfer_qty, total_stock_qty,
                   status, generated_on, generated_by
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
    """The dynamic store column set for a build — every store that took part,
    including one whose VPL was empty (it still shows stock)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT bs.store_id, st.store_code, st.store_name,
                   bs.is_warehouse, bs.refresh_id, bs.vpl_product_count,
                   bs.vpl_generated_on
            FROM procurement.product_intelligence_build_store bs
            LEFT JOIN dbo.stores st ON st.store_id = bs.store_id
            WHERE bs.build_id = ?
            ORDER BY bs.is_warehouse DESC, st.store_code
            """,
            (build_id,),
        )
        return [_stringify(r) for r in _rows_to_dicts(cur)]
    finally:
        conn.close()


def grid_rows(build_id):
    """All consolidated (canonical supplier product) rows for a build."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT cache_id, common_product_id, product_code, product_name,
                   manufacturer_id,
                   supplier_code, supplier_product_code, supplier_product_name,
                   consolidated_suggest_qty, consolidated_purchase_qty,
                   consolidated_stock_qty, transfer_qty, mapped_store_count,
                   warehouse_stock_qty, warehouse_product_code, warehouse_suggest_qty,
                   total_sales_qty, total_purchase_qty,
                   priority, priority_rank, stockout_store_count,
                   confidence, match_method,
                   mrp, ptr_cost, last_purchase_rate, margin, offer_text
            FROM procurement.product_intelligence_cache
            WHERE build_id = ?
            ORDER BY priority_rank DESC, consolidated_purchase_qty DESC, product_name
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
                   avg_sale, sales_qty, purchase_qty, days_cover, in_vpl,
                   last_sale_date, last_purchase_date, non_moving_days,
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
                   supplier_code, supplier_product_code, supplier_product_name,
                   consolidated_suggest_qty, consolidated_purchase_qty,
                   consolidated_stock_qty, transfer_qty, mapped_store_count,
                   warehouse_stock_qty, warehouse_product_code, warehouse_suggest_qty,
                   total_sales_qty, total_purchase_qty,
                   priority, priority_rank, stockout_store_count,
                   confidence, match_method,
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
                   s.sales_qty, s.purchase_qty, s.days_cover,
                   s.in_vpl, s.is_warehouse,
                   s.last_sale_date, s.last_purchase_date, s.non_moving_days
            FROM procurement.product_intelligence_store s
            LEFT JOIN dbo.stores st ON st.store_id = s.store_id
            WHERE s.cache_id = ?
            ORDER BY s.is_warehouse DESC, st.store_code
            """,
            (cache_id,),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()


def cache_store_context(cache_id, store_id):
    """The store's ProductCode for one canonical product (drives the history
    read). None when the product is not mapped in that store."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.store_id, s.product_code, s.product_name,
                   s.stock_qty, s.suggested_qty, s.avg_sale,
                   s.sales_qty, s.purchase_qty, s.in_vpl,
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
# Per-store history  (on-demand only — reuses the proven stock.usp_* procedures)
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


def monthly_sales(tenant_id, store_id, product_code, months=12):
    """Monthly sold quantity for ONE store's ProductCode (the detail chart)."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT FORMAT(psi.TransactionDate, 'yyyy-MM') AS period,
                   CAST(SUM(ISNULL(psi.Quantity, 0)) AS DECIMAL(18,3)) AS qty
            FROM sync.ProductSaleInformation psi
            WHERE psi.tenant_id = ? AND psi.store_id = ?
              AND psi.ProductCode = ?
              AND ISNULL(psi.TransactionValidity, 0) = 0
              AND psi.TransactionDate >= DATEADD(month, -?, GETDATE())
            GROUP BY FORMAT(psi.TransactionDate, 'yyyy-MM')
            ORDER BY period
            """,
            (tenant_id, store_id, int(product_code), int(months)),
        )
        return _floatify(_rows_to_dicts(cur))
    finally:
        conn.close()


# ==========================================================================
# Per-store chart panel — resolved BY PRODUCT NAME, each store independently
# ==========================================================================
#
# The legacy VB.NET analyser opened each store's database separately and looked
# the product up by NAME. We keep that behaviour: the stores are one master DB
# here, but each store is still resolved on its own by ProductName — the mapping
# is NOT used for this panel, so what a store shows never depends on whether the
# product happens to be mapped.

def resolve_by_product_name(tenant_id, store_ids, product_name):
    """{store_id: {product_code, product_name}} — the store's own ProductCode for
    a product NAME. Exact name first; a store with no exact hit falls back to a
    contains match (the analyser's behaviour), taking the shortest name so
    "CROCIN 500" does not resolve to "CROCIN 500 ADVANCE PLUS"."""
    name = (product_name or "").strip()
    if not name or not store_ids:
        return {}
    marks = ", ".join(["?"] * len(store_ids))
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT store_id,
                   CAST(ProductCode AS VARCHAR(100)) AS product_code,
                   ProductName                       AS product_name,
                   CASE WHEN ProductName = ? THEN 0 ELSE 1 END AS rank_exact,
                   LEN(ProductName) AS name_len
            FROM sync.Products
            WHERE tenant_id = ? AND store_id IN ({marks})
              AND ISNULL(isActive, 1) = 1
              AND (ProductName = ? OR ProductName LIKE '%' + ? + '%')
            ORDER BY rank_exact, name_len
            """,
            (name, tenant_id, *store_ids, name, name),
        )
        out = {}
        for r in [_stringify(x) for x in _rows_to_dicts(cur)]:
            # ORDER BY puts the exact / shortest match first for each store.
            out.setdefault(r["store_id"], {
                "product_code": r["product_code"],
                "product_name": r["product_name"],
            })
        return out
    finally:
        conn.close()


def monthly_transactions(tenant_id, pairs, months=4):
    """Monthly sales + purchase quantities for many (store_id, product_code)
    pairs in ONE read — so every store's chart is drawn from a single query
    rather than one round trip per store.

    ``pairs`` is [(store_id, product_code)]. Returns
    [{store_id, period, sales_qty, purchase_qty}] over the last ``months``.
    """
    pairs = [(s, c) for s, c in pairs if c is not None and str(c).strip().isdigit()]
    if not pairs:
        return []
    values = ", ".join(["(CAST(? AS UNIQUEIDENTIFIER), CAST(? AS INT))"] * len(pairs))
    params = []
    for store_id, code in pairs:
        params.extend([store_id, int(code)])
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            WITH target(store_id, product_code) AS (
                SELECT * FROM (VALUES {values}) v(store_id, product_code)
            ),
            sales AS (
                SELECT t.store_id,
                       FORMAT(psi.TransactionDate, 'yyyy-MM') AS period,
                       SUM(ISNULL(psi.Quantity, 0)) AS qty
                FROM target t
                JOIN sync.ProductSaleInformation psi
                  ON psi.store_id = t.store_id AND psi.ProductCode = t.product_code
                WHERE psi.tenant_id = ?
                  AND ISNULL(psi.TransactionValidity, 0) = 0
                  AND psi.TransactionDate >= DATEADD(month, -?, GETDATE())
                GROUP BY t.store_id, FORMAT(psi.TransactionDate, 'yyyy-MM')
            ),
            purch AS (
                SELECT t.store_id,
                       FORMAT(pt.grndate, 'yyyy-MM') AS period,
                       SUM(ISNULL(pt.stockreceived, 0) + ISNULL(pt.FreeQty, 0)) AS qty
                FROM target t
                JOIN sync.PurchaseTrans pt
                  ON pt.store_id = t.store_id AND pt.ProductCode = t.product_code
                WHERE pt.tenant_id = ?
                  AND pt.grndate >= DATEADD(month, -?, GETDATE())
                GROUP BY t.store_id, FORMAT(pt.grndate, 'yyyy-MM')
            )
            SELECT CAST(COALESCE(s.store_id, p.store_id) AS VARCHAR(50)) AS store_id,
                   COALESCE(s.period, p.period)                          AS period,
                   CAST(ISNULL(s.qty, 0) AS DECIMAL(18,3))               AS sales_qty,
                   CAST(ISNULL(p.qty, 0) AS DECIMAL(18,3))               AS purchase_qty
            FROM sales s
            FULL OUTER JOIN purch p
              ON p.store_id = s.store_id AND p.period = s.period
            ORDER BY store_id, period
            """,
            (*params, tenant_id, int(months), tenant_id, int(months)),
        )
        return _floatify([_stringify(r) for r in _rows_to_dicts(cur)])
    finally:
        conn.close()
