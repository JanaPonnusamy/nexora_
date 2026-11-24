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

SCHEMA_VERSION = 1

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
