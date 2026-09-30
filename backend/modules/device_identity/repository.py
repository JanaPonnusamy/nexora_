"""Data access for device registrations + device->store assignments."""

from config.database import get_connection


def ensure_schema():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            IF OBJECT_ID('dbo.device_registrations', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.device_registrations (
                    device_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_device_registrations PRIMARY KEY,
                    device_fingerprint NVARCHAR(200) NOT NULL,
                    machine_name NVARCHAR(200) NULL,
                    public_key NVARCHAR(MAX) NOT NULL,
                    key_algo NVARCHAR(30) NOT NULL CONSTRAINT DF_device_reg_algo DEFAULT ('ED25519'),
                    app_type NVARCHAR(30) NULL,
                    app_version NVARCHAR(50) NULL,
                    registered_by_user_id UNIQUEIDENTIFIER NULL,
                    registered_by_username NVARCHAR(200) NULL,
                    tenant_id UNIQUEIDENTIFIER NULL,
                    status NVARCHAR(30) NOT NULL CONSTRAINT DF_device_reg_status DEFAULT ('active'),
                    revoked_at DATETIME2(0) NULL,
                    last_seen_at DATETIME2(0) NULL,
                    created_at DATETIME2(0) NOT NULL CONSTRAINT DF_device_reg_created DEFAULT SYSUTCDATETIME(),
                    updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_device_reg_updated DEFAULT SYSUTCDATETIME()
                );
            END;

            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID('dbo.device_registrations')
                  AND name = 'UX_device_registrations_fingerprint'
            )
            BEGIN
                CREATE UNIQUE INDEX UX_device_registrations_fingerprint
                    ON dbo.device_registrations(device_fingerprint);
            END;

            IF OBJECT_ID('dbo.device_store_assignments', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.device_store_assignments (
                    assignment_id INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_device_store_assignments PRIMARY KEY,
                    device_id UNIQUEIDENTIFIER NOT NULL,
                    store_id UNIQUEIDENTIFIER NOT NULL,
                    tenant_id UNIQUEIDENTIFIER NULL,
                    assigned_by UNIQUEIDENTIFIER NULL,
                    assigned_at DATETIME2(0) NOT NULL CONSTRAINT DF_dsa_assigned DEFAULT SYSUTCDATETIME(),
                    is_active BIT NOT NULL CONSTRAINT DF_dsa_active DEFAULT (1)
                );
            END;

            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID('dbo.device_store_assignments')
                  AND name = 'UX_device_store_assignments'
            )
            BEGIN
                CREATE UNIQUE INDEX UX_device_store_assignments
                    ON dbo.device_store_assignments(device_id, store_id);
            END;
            """
        )
        conn.commit()
    finally:
        conn.close()


def register_device(device_fingerprint, public_key, key_algo, machine_name,
                    app_type, app_version, user):
    """Upsert by fingerprint. Re-registering the same machine rotates its key
    and reactivates it (status='active'). Returns (device_id, is_new)."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE dbo.device_registrations AS target
            USING (SELECT ? AS device_fingerprint) AS source
            ON target.device_fingerprint = source.device_fingerprint
            WHEN MATCHED THEN UPDATE SET
                public_key = ?, key_algo = ?, machine_name = ?,
                app_type = ?, app_version = ?,
                registered_by_user_id = ?, registered_by_username = ?, tenant_id = ?,
                status = 'active', revoked_at = NULL, updated_at = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN INSERT
                (device_id, device_fingerprint, public_key, key_algo, machine_name,
                 app_type, app_version, registered_by_user_id, registered_by_username, tenant_id)
                VALUES (NEWID(), ?, ?, ?, ?, ?, ?, ?, ?, ?)
            OUTPUT INSERTED.device_id, $action;
            """,
            device_fingerprint,
            public_key, key_algo, machine_name, app_type, app_version,
            _uid(user.get("sub")), user.get("username"), _uid(user.get("tenant_id")),
            device_fingerprint, public_key, key_algo, machine_name, app_type, app_version,
            _uid(user.get("sub")), user.get("username"), _uid(user.get("tenant_id")),
        )
        row = cur.fetchone()
        device_id, action = str(row[0]), row[1]
        conn.commit()

        # Convenience bootstrap: auto-assign the registering store-user's own
        # store so the agent can sync immediately after setup. Super admins add
        # more stores from HO. Skipped for users with no store (e.g. platform).
        store_id = user.get("store_id")
        if store_id:
            _assign_store(conn, device_id, store_id, user.get("tenant_id"), user.get("sub"))

        return device_id, (action == "INSERT")
    finally:
        conn.close()


def get_device(device_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT device_id, device_fingerprint, machine_name, public_key, key_algo,
                   app_type, app_version, status, tenant_id
            FROM dbo.device_registrations WHERE device_id = ?
            """,
            device_id,
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "device_id": str(row[0]),
            "device_fingerprint": row[1],
            "machine_name": row[2],
            "public_key": row[3],
            "key_algo": row[4],
            "app_type": row[5],
            "app_version": row[6],
            "status": row[7],
            "tenant_id": str(row[8]) if row[8] else None,
        }
    finally:
        conn.close()


def touch_last_seen(device_id, app_version=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        if app_version:
            cur.execute(
                "UPDATE dbo.device_registrations SET last_seen_at = SYSUTCDATETIME(), "
                "app_version = ?, updated_at = SYSUTCDATETIME() WHERE device_id = ?",
                app_version, device_id,
            )
        else:
            cur.execute(
                "UPDATE dbo.device_registrations SET last_seen_at = SYSUTCDATETIME() "
                "WHERE device_id = ?",
                device_id,
            )
        conn.commit()
    finally:
        conn.close()


def revoke_device(device_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.device_registrations SET status = 'revoked', "
            "revoked_at = SYSUTCDATETIME(), updated_at = SYSUTCDATETIME() WHERE device_id = ?",
            device_id,
        )
        affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()


def list_devices():
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.device_id, d.device_fingerprint, d.machine_name, d.app_type,
                   d.app_version, d.status, d.tenant_id, d.registered_by_username,
                   d.last_seen_at, d.created_at
            FROM dbo.device_registrations d
            ORDER BY d.created_at DESC
            """
        )
        devices = []
        for r in cur.fetchall():
            devices.append({
                "device_id": str(r[0]),
                "device_fingerprint": r[1],
                "machine_name": r[2],
                "app_type": r[3],
                "app_version": r[4],
                "status": r[5],
                "tenant_id": str(r[6]) if r[6] else None,
                "registered_by_username": r[7],
                "last_seen_at": r[8].isoformat() if r[8] else None,
                "created_at": r[9].isoformat() if r[9] else None,
                "stores": [],
            })
        # Attach assignments (store code/name) in one pass.
        cur.execute(
            """
            SELECT a.device_id, a.store_id, s.store_code, s.store_name, s.is_active
            FROM dbo.device_store_assignments a
            LEFT JOIN dbo.stores s ON s.store_id = a.store_id
            WHERE a.is_active = 1
            """
        )
        by_device = {}
        for r in cur.fetchall():
            by_device.setdefault(str(r[0]), []).append({
                "store_id": str(r[1]),
                "store_code": r[2],
                "store_name": r[3],
                "is_active": bool(r[4]) if r[4] is not None else None,
            })
        for d in devices:
            d["stores"] = by_device.get(d["device_id"], [])
        return devices
    finally:
        conn.close()


def assign_store(device_id, store_id, tenant_id, assigned_by):
    ensure_schema()
    conn = get_connection()
    try:
        _assign_store(conn, device_id, store_id, tenant_id, assigned_by)
    finally:
        conn.close()


def unassign_store(device_id, store_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE dbo.device_store_assignments SET is_active = 0 "
            "WHERE device_id = ? AND store_id = ?",
            device_id, store_id,
        )
        affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()


def get_assigned_store_ids(device_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT store_id FROM dbo.device_store_assignments "
            "WHERE device_id = ? AND is_active = 1",
            device_id,
        )
        return [str(r[0]) for r in cur.fetchall()]
    finally:
        conn.close()


def get_assigned_stores_with_config(device_id):
    """Every store assigned to the device, each with its agent-config (DB
    connection). This is what the multi-store agent pulls each cycle."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.store_id, s.tenant_id, s.store_code, s.store_name,
                   s.server_name, s.database_name, s.username, s.password_encrypted,
                   s.connection_type, s.agent_version, s.is_active
            FROM dbo.device_store_assignments a
            JOIN dbo.stores s ON s.store_id = a.store_id
            WHERE a.device_id = ? AND a.is_active = 1
            ORDER BY s.store_order, s.store_code
            """,
            device_id,
        )
        stores = []
        for r in cur.fetchall():
            stores.append({
                "store_id": str(r[0]),
                "tenant_id": str(r[1]) if r[1] else None,
                "store_code": r[2],
                "store_name": r[3],
                "server_name": r[4],
                "database_name": r[5],
                "username": r[6],
                "password_encrypted": r[7].hex() if r[7] else None,
                "connection_type": r[8],
                "agent_version": r[9],
                "is_active": bool(r[10]),
            })
        return stores
    finally:
        conn.close()


# ---- internals ------------------------------------------------------------

def _assign_store(conn, device_id, store_id, tenant_id, assigned_by):
    """Idempotent assign (reactivates a previously-unassigned row). Shares the
    caller's connection so register_device can bootstrap in one transaction."""
    cur = conn.cursor()
    cur.execute(
        """
        MERGE dbo.device_store_assignments AS target
        USING (SELECT CAST(? AS UNIQUEIDENTIFIER) AS device_id,
                      CAST(? AS UNIQUEIDENTIFIER) AS store_id) AS source
        ON target.device_id = source.device_id AND target.store_id = source.store_id
        WHEN MATCHED THEN UPDATE SET is_active = 1, assigned_at = SYSUTCDATETIME(),
            tenant_id = ?, assigned_by = ?
        WHEN NOT MATCHED THEN INSERT (device_id, store_id, tenant_id, assigned_by)
            VALUES (?, ?, ?, ?);
        """,
        device_id, store_id,
        _uid(tenant_id), _uid(assigned_by),
        device_id, store_id, _uid(tenant_id), _uid(assigned_by),
    )
    conn.commit()


def _uid(value):
    """Pass GUID-ish values through as-is; treat empty/placeholder as NULL so a
    non-GUID (e.g. a platform user's blank tenant) doesn't blow up the cast."""
    if value in (None, "", "None"):
        return None
    return str(value)
