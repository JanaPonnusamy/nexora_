"""Store Need view + day-scoped supplier assignment for Supplier Stock Analysis.

Store Need answers "the warehouse has none, this supplier has it, and the
branches are selling it - how much does each branch need for a month?":
  * supplier lines (OrderNMC.SupplierStock, stock > 0) of the selected
    warehouse whose resolved warehouse product has live stock <= 0;
  * each branch's product linked to that warehouse product through
    dbo.product_mapping, both directions - APPROVED/AUTO, or PENDING with the
    same code (the shared Shopaid master; same trust rule as the HO stock
    bridge, product_mapping.repository.supplier_bridge_targets);
  * branch retail movement over the last 90 days (sold in the last 30 days
    and in >= MIN_BILLS bills); need = 90-day sales / 3 - branch stock, in
    packs (SaleUnit).
Stock everywhere is the latest sync.ProductTrans.StockInHand (_dbutil).

Assignments record "this warehouse product is being ordered from supplier X
today", so the same product shows as already assigned under every other
supplier. Only today's rows count; older ones are simply ignored.
"""

import math
import threading
from datetime import date
from time import monotonic

from config.database import get_connection
from modules.procurement._dbutil import rows_to_dicts, store_stock_expr
from modules.supplier_stock_analysis.repository import _supplier_stock_source

SALES_DAYS = 90
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


_CACHE_TTL_SECONDS = 15 * 60
_need_cache = {}
_need_locks = {}
_locks_guard = threading.Lock()


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
    warehouse product ANY supplier holds. Supplier-independent, so it is
    computed once (~15s: 90 days of branch sales) and cached; switching
    supplier is then instant."""
    key = (str(tenant_id).upper(), str(store_id).upper())
    with _locks_guard:
        lock = _need_locks.setdefault(key, threading.Lock())
    with lock:
        hit = _need_cache.get(key)
        if hit and hit[0] > monotonic():
            return hit[1]
        value = _compute_branch_need(tenant_id, store_id)
        _need_cache[key] = (monotonic() + _CACHE_TTL_SECONDS, value)
        return value


def _compute_branch_need(tenant_id, store_id):
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
        # tenant_id + store_id + ProductCode = IX_ProductSaleInformation_Product seek.
        cur.execute(
            f"""
            WITH sales AS (
                SELECT r.wh_code, r.sid, r.code,
                       SUM(ps.Quantity) AS q90,
                       SUM(CASE WHEN ps.TransactionDate >= DATEADD(day, -{RECENT_DAYS}, CAST(GETDATE() AS date))
                                THEN ps.Quantity ELSE 0 END) AS q30,
                       COUNT(DISTINCT ps.Bnumber) AS bills90,
                       MAX(ps.TransactionDate) AS last_sale
                FROM #r r
                JOIN sync.ProductSaleInformation ps
                  ON ps.tenant_id = ? AND ps.store_id = r.sid AND ps.ProductCode = r.code
                WHERE ps.TransactionDate >= DATEADD(day, -{SALES_DAYS}, CAST(GETDATE() AS date))
                  AND ps.SeriesTransID = 1 AND ps.TransactionValidity = 0
                  AND ISNULL(ps.DontConsiderInOrder, 0) = 0 AND ps.Quantity > 0
                GROUP BY r.wh_code, r.sid, r.code
            )
            SELECT s.wh_code, st.store_code, s.q90, s.q30, s.bills90, s.last_sale,
                   ISNULL(p.SaleUnit, 1) AS sale_unit,
                   {store_stock_expr('p')} AS store_stock
            FROM sales s
            JOIN dbo.stores st ON st.store_id = s.sid
            LEFT JOIN sync.Products p ON p.tenant_id = ? AND p.store_id = s.sid AND p.ProductCode = s.code
            """,
            (tenant_id, tenant_id),
        )
        movement = rows_to_dicts(cur)
    finally:
        conn.close()

    # Several branch codes can map onto one warehouse product: combine per branch.
    per = {}
    for m in movement:
        key = (m["wh_code"], (m["store_code"] or "").strip())
        agg = per.setdefault(key, {"q90": 0, "q30": 0, "bills90": 0, "stock": 0, "sale_unit": 1})
        agg["q90"] += float(m["q90"] or 0)
        agg["q30"] += float(m["q30"] or 0)
        agg["bills90"] += int(m["bills90"] or 0)
        agg["stock"] += float(m["store_stock"] or 0)
        agg["sale_unit"] = max(agg["sale_unit"], float(m["sale_unit"] or 1), 1)

    by_code = {}
    for (wh_code, store_code), a in per.items():
        if a["q30"] <= 0 or a["bills90"] < MIN_BILLS:
            continue
        month_need = math.ceil(a["q90"] / 3)
        packs = math.ceil(max(month_need - a["stock"], 0) / a["sale_unit"])
        if packs <= 0:
            continue
        by_code.setdefault(wh_code, {})[store_code] = {
            "need_packs": packs,
            "month_need_units": month_need,
            "store_stock": a["stock"],
            "sold_90d": a["q90"],
            "sold_30d": a["q30"],
            "bills_90d": a["bills90"],
            "sale_unit": a["sale_unit"],
            "movement": "Fast" if a["bills90"] >= FAST_BILLS else "Medium",
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
