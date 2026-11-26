"""SQLite schema for the per-store, single-order-scoped local cache.

Design doc: docs/order-sync-redesign/Order_Sync_Redesign_Plan.md section 3.3.
Standalone module -- no imports from supplier-stock-client or any other
MediQ module; everything this needs is copied in here.

The file is intentionally disposable: one order's worth of data only,
replaced wholesale on every Order Process push (see builder.py). Nothing in
this schema is designed to survive past the order it was built for except
pending write-back rows, which builder.py's replace step waits to drain
first.
"""

SCHEMA_VERSION = 3

CREATE_SQL = """
PRAGMA journal_mode = WAL;

-- One row per order line (Qty Check grid), current order only. Column list
-- matches exactly what repository.assigned_orders / qty_check reads use --
-- see repository.py:1476 (assigned_orders) for the verified real column set.
CREATE TABLE IF NOT EXISTS order_lines (
    product_code        TEXT NOT NULL,
    product_name        TEXT,
    order_qty           REAL NOT NULL DEFAULT 0,
    org_order_qty        REAL NOT NULL DEFAULT 0,
    sale_unit           TEXT,
    mrp                 REAL,
    purchase_price       REAL,
    total_stock          REAL,
    sls_qty              REAL,
    unit_description      TEXT,
    wanted_type          TEXT,
    product_type_name     TEXT,
    remarks             TEXT,
    is_offer             INTEGER NOT NULL DEFAULT 0,
    qty_check            INTEGER NOT NULL DEFAULT 0,
    status              INTEGER NOT NULL DEFAULT 0,
    or_supplier          TEXT,
    or_supplier_code       TEXT,
    supplier_product_code   TEXT,
    supplier_product_name   TEXT,
    -- Sync watermark (added schema v2): when this row last changed locally
    -- and whether that change has reached HO yet. 'synced_at' is stamped by
    -- writeback.drain() the moment the row's pending_writeback entries clear
    -- -- it is NOT set at build time, so a freshly built cache (no local
    -- edits yet) correctly reads as "nothing pending" with synced_at NULL
    -- until the first local edit+drain cycle touches it.
    updated_at           TEXT,
    synced_at            TEXT,
    PRIMARY KEY (product_code)
);

-- Per-product order history (last 5 OrderManagementBackup rows for that
-- product -- repository.qty_check_order_history ported with TOP 5 instead
-- of TOP 25; see plan doc section 3.3). Read-only reference data from the
-- app's side, replaced wholesale with everything else on the next push.
CREATE TABLE IF NOT EXISTS product_history (
    product_code    TEXT NOT NULL,
    rank            INTEGER NOT NULL,  -- 1 = most recent of the 5
    or_qty          REAL,
    org_order_qty    REAL,
    sale_unit       TEXT,
    mrp             REAL,
    remarks         TEXT,
    wanted_date      TEXT,
    wanted_type      TEXT,
    or_supplier      TEXT,
    PRIMARY KEY (product_code, rank)
);

-- Export state for the current order (what's been exported / pending).
CREATE TABLE IF NOT EXISTS export_state (
    product_code    TEXT NOT NULL PRIMARY KEY,
    exported        INTEGER NOT NULL DEFAULT 0,
    exported_at      TEXT
);

-- Schema v3: what the Procurement workspace's By Supplier / Live Stock /
-- All products / compare card need, so the store PC can serve them from its
-- downloaded copy instead of re-running the slow PurchaseTrans queries on HO.
-- workspace_rows: one API-shaped row per product (every status -- the app
-- overlays live status from /orders/{store}/line-states), JSON exactly as
-- repository.all_open_orderables returns it, incl. the last-offer columns.
CREATE TABLE IF NOT EXISTS workspace_rows (
    product_code    TEXT NOT NULL PRIMARY KEY,
    row_json        TEXT NOT NULL
);

-- Every real SupplierCode that ever supplied the product (PurchaseTrans,
-- InvoiceSeries <> 'TI') -- By Supplier's "History" mode filter.
CREATE TABLE IF NOT EXISTS product_suppliers (
    product_code    TEXT NOT NULL,
    supplier_code   TEXT NOT NULL,
    PRIMARY KEY (product_code, supplier_code)
);

-- Best-stocked SupplierStock line per (product, SupplierCode) -- Live Stock
-- mode and the compare card. Refreshed on its own (builder.
-- refresh_supplier_stock) whenever SupplierStock changes after the build.
CREATE TABLE IF NOT EXISTS supplier_stock (
    product_code    TEXT NOT NULL,
    supplier_code   TEXT NOT NULL,
    line_json       TEXT NOT NULL,
    PRIMARY KEY (product_code, supplier_code)
);

-- One row, identifies which order this cache file is for and the cache's
-- own schema version (for a future migration to detect/reject a stale file
-- shape instead of guessing column names that may no longer match).
CREATE TABLE IF NOT EXISTS cache_meta (
    key     TEXT NOT NULL PRIMARY KEY,
    value   TEXT
);

-- Local edits not yet confirmed written back to central OrderNMC/OrderSMS/
-- OrderSuccess. This is the ONLY table that must survive a file replace --
-- builder.py's replace step drains this to empty (write-back succeeds)
-- before ever deleting the old file; see plan doc section 3.3 point 4.
CREATE TABLE IF NOT EXISTS pending_writeback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_code     TEXT NOT NULL,
    field           TEXT NOT NULL,   -- 'order_qty' | 'status' | 'exported' | ...
    value           TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def init_db(conn):
    conn.executescript(CREATE_SQL)
    conn.commit()
