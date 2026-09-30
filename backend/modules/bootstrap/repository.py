"""Data access for HO route discovery (dbo.ho_routes).

The route list is the ordered set of URLs a store agent / desktop client tries
to reach HO on (LAN first, then static IP, then domain/anchor). Apps cache it
and refresh it every cycle from whichever route currently answers, so moving HO
is a single UPDATE here rather than a reinstall on every store machine. The
permanent DOMAIN/ANCHOR route is what lets apps recover after a full server
rebuild at a new address (re-point the name, every app follows).
"""

from config.database import get_connection

# Seeded once on first use so a fresh HO already advertises the currently-known
# routes. Editable afterwards from the table / HO UI; seeding never overwrites
# an existing row (idempotent, matched on url).
_SEED_ROUTES = [
    ("LAN", "http://192.168.10.73:8000", 1),
    ("STATIC", "http://122.252.246.181:8000", 2),
    ("DOMAIN", "https://ho.qvault.in", 3),
]


def ensure_schema():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            IF OBJECT_ID('dbo.ho_routes', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.ho_routes (
                    route_id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_ho_routes PRIMARY KEY,
                    label NVARCHAR(50) NOT NULL,
                    url NVARCHAR(500) NOT NULL,
                    route_order INT NOT NULL CONSTRAINT DF_ho_routes_order DEFAULT (100),
                    is_active BIT NOT NULL CONSTRAINT DF_ho_routes_active DEFAULT (1),
                    updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_ho_routes_updated DEFAULT SYSUTCDATETIME()
                );
            END;

            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID('dbo.ho_routes')
                  AND name = 'UX_ho_routes_url'
            )
            BEGIN
                CREATE UNIQUE INDEX UX_ho_routes_url ON dbo.ho_routes(url);
            END;
            """
        )
        conn.commit()

        # Seed only if the table is completely empty, so an operator who has
        # curated the list (removed a route, changed an order) never gets the
        # defaults re-injected behind their back.
        cur.execute("SELECT COUNT(*) FROM dbo.ho_routes")
        if cur.fetchone()[0] == 0:
            for label, url, order in _SEED_ROUTES:
                cur.execute(
                    "INSERT INTO dbo.ho_routes (label, url, route_order) VALUES (?, ?, ?)",
                    label, url, order,
                )
            conn.commit()
    finally:
        conn.close()


def get_active_routes():
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT label, url, route_order, updated_at
            FROM dbo.ho_routes
            WHERE is_active = 1
            ORDER BY route_order, route_id
            """
        )
        return [
            {
                "label": r[0],
                "url": r[1],
                "order": r[2],
                "updated_at": r[3].isoformat() if r[3] else None,
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


# ---- admin management (super-admin maintenance UI) ------------------------

def list_all_routes():
    """Every route incl. inactive, with ids, for the maintenance UI."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT route_id, label, url, route_order, is_active, updated_at
            FROM dbo.ho_routes
            ORDER BY route_order, route_id
            """
        )
        return [
            {
                "route_id": r[0],
                "label": r[1],
                "url": r[2],
                "route_order": r[3],
                "is_active": bool(r[4]),
                "updated_at": r[5].isoformat() if r[5] else None,
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()


def add_route(label, url, route_order=100, is_active=True):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        # De-dupe on url: adding an existing url just re-activates / re-orders it
        # rather than erroring on the unique index.
        cur.execute(
            """
            MERGE dbo.ho_routes AS target
            USING (SELECT ? AS url) AS source ON target.url = source.url
            WHEN MATCHED THEN UPDATE SET label = ?, route_order = ?, is_active = ?,
                updated_at = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN INSERT (label, url, route_order, is_active)
                VALUES (?, ?, ?, ?)
            OUTPUT INSERTED.route_id;
            """,
            (url.strip().rstrip("/"), label, route_order, 1 if is_active else 0,
             label, url.strip().rstrip("/"), route_order, 1 if is_active else 0),
        )
        route_id = cur.fetchone()[0]
        conn.commit()
        return route_id
    finally:
        conn.close()


def update_route(route_id, label=None, url=None, route_order=None, is_active=None):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.ho_routes SET
                label = COALESCE(?, label),
                url = COALESCE(?, url),
                route_order = COALESCE(?, route_order),
                is_active = COALESCE(?, is_active),
                updated_at = SYSUTCDATETIME()
            WHERE route_id = ?
            """,
            (label,
             url.strip().rstrip("/") if url else None,
             route_order,
             None if is_active is None else (1 if is_active else 0),
             route_id),
        )
        affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()


def delete_route(route_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM dbo.ho_routes WHERE route_id = ?", route_id)
        affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()
