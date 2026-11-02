"""Store Need view + day-scoped supplier assignment for Supplier Stock Analysis.

Store Need answers "the warehouse has none, this supplier has it, and the
branches are selling it - how much does each branch need for a month?":
  * supplier lines (OrderNMC.SupplierStock, stock > 0) of the selected
    warehouse whose resolved warehouse product has live stock <= 0;
  * each branch's product linked to that warehouse product through
    dbo.product_mapping, both directions - APPROVED/AUTO, or PENDING with the
    same code (the shared Shopaid master; same trust rule as the HO stock
    bridge, product_mapping.repository.supplier_bridge_targets);
  * branch movement from monthly sync.ProductTrans (last 3 whole months +
    this month to date; net of returns; last sale within 30 days and
    >= MIN_BILLS sale transactions); need = monthly-average sales - branch
    stock, in packs (SaleUnit).
Stock everywhere is the latest sync.ProductTrans.StockInHand (_dbutil).

Assignments record "this warehouse product is being ordered from supplier X
today", so the same product shows as already assigned under every other
supplier. Only today's rows count; older ones are simply ignored.
"""

import logging
import math
import sys
import threading
from datetime import date, datetime, timedelta
from time import monotonic

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts, store_stock_expr
from modules.supplier_stock_analysis.repository import _supplier_stock_source

logger = logging.getLogger(__name__)

RECENT_DAYS = 30
MIN_BILLS = 3
FAST_BILLS = 6


def _ensure_assignment_table(cur):
    cur.execute(
        """
        IF OBJECT_ID('dbo.supplier_stock_assignment') IS NULL
        CREATE TABLE dbo.supplier_stock_assignment (
            tenant_id         uniqueidentifier NOT NULL,
            store_id          uniqueidentifier NOT NULL,
            assigned_on       date             NOT NULL,
            product_code      varchar(50)      NOT NULL,
            supplier_code     varchar(100)     NOT NULL,
            supplier_stock_id varchar(400)     NULL,
            supplier_product_name varchar(300) NULL,
            qty               varchar(20)      NOT NULL,
            remarks           nvarchar(400)    NULL,
            assigned_by       nvarchar(150)    NULL,
            updated_at        datetime         NOT NULL DEFAULT GETDATE(),
            CONSTRAINT PK_supplier_stock_assignment
                PRIMARY KEY (tenant_id, store_id, assigned_on, product_code, supplier_code)
        );
        """
    )


# The HO SQL Server is Express (~1.4 GB buffer pool, page life expectancy of
# seconds), so this computation swings from ~1s to ~2 min with cache state.
# Keep it off the request path: a background thread refreshes every
# warehouse requested in the last few hours, requests get the last result
# immediately (even if older than the refresh interval), and the warehouses
# are pre-warmed shortly after the backend starts. Only a request that finds
# no result at all computes inline.
_REFRESH_SECONDS = 10 * 60
_KEEP_WARM_SECONDS = 6 * 3600
_need_cache = {}        # key -> (computed_at monotonic, value)
_last_requested = {}    # key -> monotonic of last request
_need_locks = {}
_locks_guard = threading.Lock()
_refresher_started = False


def _supplier_lines(cur, tenant_id, store_id, supplier_code=None):
    """In-stock supplier lines on warehouse products with live stock <= 0
    (one supplier, or every supplier when supplier_code is None)."""
    supplier_clause = "AND ss.supplier_code = ?" if supplier_code else ""
    params = (tenant_id, store_id) + ((supplier_code,) if supplier_code else ())
    cur.execute(
        f"""
        SELECT ss.supplier_stock_id, CAST(ss.product_code AS VARCHAR(50)) AS product_code,
               {store_stock_expr('p')} AS warehouse_stock
        FROM {_supplier_stock_source()} ss
        JOIN sync.Products p
          ON p.tenant_id = ss.tenant_id AND p.store_id = ss.store_id
         AND p.productcode = TRY_CAST(ss.product_code AS INT)
        WHERE ss.tenant_id = ? AND ss.store_id = ? {supplier_clause}
          AND ISNULL(ss.available_stock, 0) > 0
        """,
        params,
    )
    return [r for r in rows_to_dicts(cur) if float(r["warehouse_stock"] or 0) <= 0]


def store_need(tenant_id, store_id, supplier_code):
    need_by_code = _branch_need(tenant_id, store_id)
    conn = get_connection()
    try:
        lines = _supplier_lines(conn.cursor(), tenant_id, store_id, supplier_code)
    finally:
        conn.close()
    rows, stores = [], set()
    for line in lines:
        need = need_by_code.get(line["product_code"])
        if not need:
            continue
        stores.update(need)
        rows.append({
            "supplier_stock_id": line["supplier_stock_id"],
            "product_code": line["product_code"],
            "warehouse_stock": float(line["warehouse_stock"] or 0),
            "total_need": sum(n["need_packs"] for n in need.values()),
            "bills_90d": sum(n["bills_90d"] for n in need.values()),
            "movement": "Fast" if any(n["movement"] == "Fast" for n in need.values()) else "Medium",
            "stores": need,
        })
    return {"rows": rows, "stores": sorted(stores)}


def _branch_need(tenant_id, store_id):
    """{warehouse product_code: {branch_code: need}} for every zero-stock
    warehouse product ANY supplier holds. Supplier-independent, so switching
    supplier never recomputes; see the cache notes above."""
    key = (str(tenant_id).upper(), str(store_id).upper())
    _last_requested[key] = monotonic()
    _start_refresher()
    hit = _need_cache.get(key)
    if hit:
        return hit[1]
    return _refresh(key)


def _refresh(key):
    with _locks_guard:
        lock = _need_locks.setdefault(key, threading.Lock())
    with lock:
        hit = _need_cache.get(key)
        if hit and monotonic() - hit[0] < 60:   # refreshed while we waited
            return hit[1]
        value = _compute_branch_need(*key)
        _need_cache[key] = (monotonic(), value)
        return value


def _refresher_loop():
    import time
    time.sleep(20)  # let the backend finish starting
    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT CAST(tenant_id AS VARCHAR(36)), CAST(store_id AS VARCHAR(36)) "
                        "FROM dbo.stores WHERE is_warehouse = 1 AND ISNULL(is_active, 1) = 1")
            for tenant_id, store_id in cur.fetchall():
                _last_requested.setdefault((tenant_id.upper(), store_id.upper()), monotonic())
        finally:
            conn.close()
    except Exception:
        logger.warning("store-need prewarm: could not list warehouses", exc_info=True)
    while True:
        for key, requested in list(_last_requested.items()):
            if monotonic() - requested > _KEEP_WARM_SECONDS:
                continue
            hit = _need_cache.get(key)
            if hit and monotonic() - hit[0] < _REFRESH_SECONDS:
                continue
            try:
                _refresh(key)
            except Exception:
                logger.warning("store-need refresh failed for %s", key, exc_info=True)
        time.sleep(30)


def _start_refresher():
    global _refresher_started
    with _locks_guard:
        if _refresher_started:
            return
        _refresher_started = True
    threading.Thread(target=_refresher_loop, name="store-need-refresher", daemon=True).start()


# Pre-warm only inside the running API server (not tests/scripts importing this).
if "uvicorn" in sys.modules:
    _start_refresher()


def _compute_branch_need(tenant_id, store_id):
    today = date.today()
    month = today.month - 3
    window_start = date(today.year + (month - 1) // 12, (month - 1) % 12 + 1, 1)
    window_days = (today - window_start).days + 1
    conn = get_connection()
    try:
        cur = conn.cursor()
        lines = _supplier_lines(cur, tenant_id, store_id)
        if not lines:
            return {}

        cur.execute("CREATE TABLE #wk (code varchar(50) COLLATE DATABASE_DEFAULT PRIMARY KEY)")
        cur.fast_executemany = True
        cur.executemany("INSERT INTO #wk (code) VALUES (?)", [(c,) for c in {r["product_code"] for r in lines}])
        cur.fast_executemany = False

        # Warehouse product -> each branch product (one warehouse code per
        # branch product, best status first), then that branch's movement.
        # Created unparameterized: a parameterized SELECT INTO runs inside
        # sp_executesql and its #table would vanish with that batch.
        cur.execute(
            """
            CREATE TABLE #pairs (wh_code varchar(50) COLLATE DATABASE_DEFAULT, sid uniqueidentifier,
                                 code varchar(50) COLLATE DATABASE_DEFAULT, status varchar(20), confidence float)
            """
        )
        cur.execute(
            """
            INSERT INTO #pairs (wh_code, sid, code, status, confidence)
            SELECT wh_code, sid, code, status, confidence FROM (
                SELECT LTRIM(RTRIM(pm.source_product_code)) AS wh_code, pm.target_store_id AS sid,
                       LTRIM(RTRIM(pm.target_product_code)) AS code, pm.status, pm.confidence
                FROM dbo.product_mapping pm JOIN #wk ON #wk.code = LTRIM(RTRIM(pm.source_product_code))
                WHERE pm.tenant_id = ? AND pm.source_store_id = ? AND pm.is_deleted = 0
                  AND pm.target_product_code IS NOT NULL
                  AND (pm.status IN ('APPROVED','AUTO')
                       OR (pm.status = 'PENDING' AND LTRIM(RTRIM(pm.source_product_code)) = LTRIM(RTRIM(pm.target_product_code))))
                UNION ALL
                SELECT LTRIM(RTRIM(pm.target_product_code)), pm.source_store_id,
                       LTRIM(RTRIM(pm.source_product_code)), pm.status, pm.confidence
                FROM dbo.product_mapping pm JOIN #wk ON #wk.code = LTRIM(RTRIM(pm.target_product_code))
                WHERE pm.tenant_id = ? AND pm.target_store_id = ? AND pm.is_deleted = 0
                  AND (pm.status IN ('APPROVED','AUTO')
                       OR (pm.status = 'PENDING' AND LTRIM(RTRIM(pm.source_product_code)) = LTRIM(RTRIM(pm.target_product_code))))
            ) x
            """,
            (tenant_id, store_id, tenant_id, store_id),
        )
        cur.execute(
            """
            CREATE TABLE #r (wh_code varchar(50) COLLATE DATABASE_DEFAULT, sid uniqueidentifier, code int,
                             PRIMARY KEY (sid, code))
            """
        )
        cur.execute(
            """
            INSERT INTO #r (wh_code, sid, code)
            SELECT wh_code, sid, code FROM (
                SELECT pr.wh_code, pr.sid, TRY_CAST(pr.code AS INT) AS code,
                       ROW_NUMBER() OVER (
                           PARTITION BY pr.sid, TRY_CAST(pr.code AS INT)
                           ORDER BY CASE pr.status WHEN 'APPROVED' THEN 0 WHEN 'AUTO' THEN 1 ELSE 2 END,
                                    pr.confidence DESC) AS rn
                FROM #pairs pr
                JOIN dbo.stores st ON st.store_id = pr.sid AND st.tenant_id = ?
                WHERE ISNULL(st.is_active, 1) = 1 AND ISNULL(st.is_warehouse, 0) = 0
                  AND TRY_CAST(pr.code AS INT) IS NOT NULL
            ) x WHERE rn = 1
            """,
            (tenant_id,),
        )
        # Monthly sync.ProductTrans rows (clustered store_id, ProductCode,
        # MonthOfStatistics = a seek, ~4 rows per product) instead of 90 days
        # of ProductSaleInformation lines: same answer at ~1/100th the I/O
        # (that scan took ~2 min on a cold HO server). Window = the last 3
        # whole months + the current month to date.
        # HASH JOIN: one pass over the window beats ~6000 random seeks on a
        # cold server (0.3s vs 8-15s measured).
        cur.execute(
            """
            CREATE TABLE #sales (wh_code varchar(50) COLLATE DATABASE_DEFAULT, sid uniqueidentifier, code int,
                                 qty float, bills int, last_sale datetime)
            """
        )
        cur.execute(
            """
            INSERT INTO #sales (wh_code, sid, code, qty, bills, last_sale)
            SELECT r.wh_code, r.sid, r.code,
                   SUM(ISNULL(pt.SaleQuantity, 0) - ISNULL(pt.SaleReturnQuantity, 0)),
                   SUM(ISNULL(pt.SaleTransactionCount, 0)),
                   MAX(pt.LastBillDate)
            FROM #r r
            JOIN sync.ProductTrans pt
              ON pt.store_id = r.sid AND pt.ProductCode = r.code
            WHERE pt.MonthOfStatistics >= ?
            GROUP BY r.wh_code, r.sid, r.code
            OPTION (HASH JOIN)
            """,
            (window_start,),
        )
        cur.execute(
            f"""
            SELECT s.wh_code, st.store_code, s.qty, s.bills, s.last_sale,
                   ISNULL(p.SaleUnit, 1) AS sale_unit,
                   {store_stock_expr('p')} AS store_stock
            FROM #sales s
            JOIN dbo.stores st ON st.store_id = s.sid
            LEFT JOIN sync.Products p ON p.tenant_id = ? AND p.store_id = s.sid AND p.ProductCode = s.code
            """,
            (tenant_id,),
        )
        movement = rows_to_dicts(cur)
    finally:
        conn.close()

    # Several branch codes can map onto one warehouse product: combine per branch.
    per = {}
    for m in movement:
        key = (m["wh_code"], (m["store_code"] or "").strip())
        agg = per.setdefault(key, {"qty": 0, "bills": 0, "stock": 0, "sale_unit": 1, "last_sale": None})
        agg["qty"] += float(m["qty"] or 0)
        agg["bills"] += int(m["bills"] or 0)
        agg["stock"] += float(m["store_stock"] or 0)
        agg["sale_unit"] = max(agg["sale_unit"], float(m["sale_unit"] or 1), 1)
        if m["last_sale"] and (agg["last_sale"] is None or m["last_sale"] > agg["last_sale"]):
            agg["last_sale"] = m["last_sale"]

    recent_cutoff = datetime.now() - timedelta(days=RECENT_DAYS)
    by_code = {}
    for (wh_code, store_code), a in per.items():
        if not a["last_sale"] or a["last_sale"] < recent_cutoff or a["bills"] < MIN_BILLS:
            continue
        month_need = math.ceil(a["qty"] * 30.4 / window_days)
        packs = math.ceil(max(month_need - a["stock"], 0) / a["sale_unit"])
        if packs <= 0:
            continue
        by_code.setdefault(wh_code, {})[store_code] = {
            "need_packs": packs,
            "month_need_units": month_need,
            "store_stock": a["stock"],
            "sold_90d": a["qty"],
            "bills_90d": a["bills"],
            "last_sale": a["last_sale"].date().isoformat(),
            "sale_unit": a["sale_unit"],
            "movement": "Fast" if a["bills"] >= FAST_BILLS else "Medium",
        }

    return by_code


def today_assignments(tenant_id, store_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_assignment_table(cur)
        conn.commit()
        cur.execute(
            """
            SELECT product_code, supplier_code, supplier_stock_id, supplier_product_name,
                   qty, remarks, assigned_by, updated_at
            FROM dbo.supplier_stock_assignment
            WHERE tenant_id = ? AND store_id = ? AND assigned_on = CAST(GETDATE() AS date)
            """,
            (tenant_id, store_id),
        )
        return {"date": date.today().isoformat(), "items": rows_to_dicts(cur)}
    finally:
        conn.close()


def save_assignments(tenant_id, store_id, supplier_code, items, assigned_by=None):
    """Upsert today's assignment per product for this supplier; a blank /
    zero qty removes it."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        _ensure_assignment_table(cur)
        saved = removed = 0
        for item in items:
            product_code = (item.get("product_code") or "").strip()
            if not product_code:
                continue
            qty = (item.get("qty") or "").strip()
            key = (tenant_id, store_id, product_code, supplier_code)
            if not qty.strip("0+ "):
                cur.execute(
                    """
                    DELETE FROM dbo.supplier_stock_assignment
                    WHERE tenant_id = ? AND store_id = ? AND assigned_on = CAST(GETDATE() AS date)
                      AND product_code = ? AND supplier_code = ?
                    """,
                    key,
                )
                removed += 1
                continue
            extra = (qty, item.get("remarks"), item.get("supplier_stock_id"),
                     item.get("supplier_product_name"), assigned_by)
            cur.execute(
                """
                MERGE dbo.supplier_stock_assignment AS t
                USING (SELECT ? AS tenant_id, ? AS store_id, CAST(GETDATE() AS date) AS assigned_on,
                              ? AS product_code, ? AS supplier_code) s
                   ON t.tenant_id = s.tenant_id AND t.store_id = s.store_id AND t.assigned_on = s.assigned_on
                  AND t.product_code = s.product_code AND t.supplier_code = s.supplier_code
                WHEN MATCHED THEN UPDATE SET qty = ?, remarks = ?, supplier_stock_id = ?,
                     supplier_product_name = ?, assigned_by = ?, updated_at = GETDATE()
                WHEN NOT MATCHED THEN INSERT (tenant_id, store_id, assigned_on, product_code, supplier_code,
                     qty, remarks, supplier_stock_id, supplier_product_name, assigned_by)
                     VALUES (s.tenant_id, s.store_id, s.assigned_on, s.product_code, s.supplier_code, ?, ?, ?, ?, ?);
                """,
                key + extra * 2,
            )
            saved += 1
        conn.commit()
        return {"saved": saved, "removed": removed}
    finally:
        conn.close()
