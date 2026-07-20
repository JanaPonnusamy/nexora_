"""Data access for managed desktop clients."""

from uuid import uuid4

from config.database import get_connection


def ensure_schema():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            IF OBJECT_ID('dbo.desktop_clients', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.desktop_clients (
                    client_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_desktop_clients PRIMARY KEY,
                    device_fingerprint NVARCHAR(200) NOT NULL,
                    machine_name NVARCHAR(200) NULL,
                    app_version NVARCHAR(50) NULL,
                    status NVARCHAR(30) NOT NULL CONSTRAINT DF_desktop_clients_status DEFAULT ('pending'),
                    tenant_id UNIQUEIDENTIFIER NULL,
                    store_id UNIQUEIDENTIFIER NULL,
                    store_code NVARCHAR(50) NULL,
                    store_name NVARCHAR(200) NULL,
                    server_base_url NVARCHAR(500) NULL,
                    enabled BIT NOT NULL CONSTRAINT DF_desktop_clients_enabled DEFAULT (0),
                    requested_store_name NVARCHAR(200) NULL,
                    requested_store_code NVARCHAR(50) NULL,
                    install_code NVARCHAR(100) NULL,
                    last_seen_at DATETIME2(0) NULL,
                    created_at DATETIME2(0) NOT NULL CONSTRAINT DF_desktop_clients_created_at DEFAULT SYSUTCDATETIME(),
                    updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_desktop_clients_updated_at DEFAULT SYSUTCDATETIME()
                );
            END;

            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE object_id = OBJECT_ID('dbo.desktop_clients')
                  AND name = 'UX_desktop_clients_fingerprint'
            )
            BEGIN
                CREATE UNIQUE INDEX UX_desktop_clients_fingerprint
                    ON dbo.desktop_clients(device_fingerprint);
            END;

            IF OBJECT_ID('dbo.desktop_client_config', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.desktop_client_config (
                    config_id TINYINT NOT NULL CONSTRAINT PK_desktop_client_config PRIMARY KEY,
                    latest_version NVARCHAR(50) NULL,
                    min_version NVARCHAR(50) NULL,
                    update_url NVARCHAR(500) NULL,
                    force_update BIT NOT NULL CONSTRAINT DF_desktop_client_config_force_update DEFAULT (0),
                    maintenance_message NVARCHAR(500) NULL,
                    updated_at DATETIME2(0) NOT NULL CONSTRAINT DF_desktop_client_config_updated_at DEFAULT SYSUTCDATETIME(),
                    CONSTRAINT CK_desktop_client_config_singleton CHECK (config_id = 1)
                );
            END;

            IF NOT EXISTS (SELECT 1 FROM dbo.desktop_client_config WHERE config_id = 1)
            BEGIN
                INSERT INTO dbo.desktop_client_config (config_id, force_update)
                VALUES (1, 0);
            END;
            """
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_dict(cursor, row):
    if not row:
        return None
    columns = [c[0] for c in cursor.description]
    data = dict(zip(columns, row))
    for key in ("client_id", "tenant_id", "store_id"):
        if data.get(key) is not None:
            data[key] = str(data[key])
    return data


def activate_request(payload):
    ensure_schema()
    client_id = str(uuid4())
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            MERGE dbo.desktop_clients AS target
            USING (
                SELECT
                    CAST(? AS UNIQUEIDENTIFIER) AS client_id,
                    ? AS device_fingerprint,
                    ? AS machine_name,
                    ? AS app_version,
                    ? AS requested_store_name,
                    ? AS requested_store_code,
                    ? AS install_code
            ) AS source
            ON target.device_fingerprint = source.device_fingerprint
            WHEN MATCHED THEN UPDATE SET
                machine_name = source.machine_name,
                app_version = source.app_version,
                requested_store_name = source.requested_store_name,
                requested_store_code = source.requested_store_code,
                install_code = source.install_code,
                status = CASE WHEN target.status = 'approved' THEN target.status ELSE 'pending' END,
                updated_at = SYSUTCDATETIME()
            WHEN NOT MATCHED THEN
                INSERT (
                    client_id, device_fingerprint, machine_name, app_version,
                    requested_store_name, requested_store_code, install_code,
                    status, enabled
                )
                VALUES (
                    source.client_id, source.device_fingerprint, source.machine_name, source.app_version,
                    source.requested_store_name, source.requested_store_code, source.install_code,
                    'pending', 0
                );
            """,
            (
                client_id,
                payload.device_fingerprint.strip(),
                payload.machine_name,
                payload.app_version,
                payload.requested_store_name,
                payload.requested_store_code,
                payload.install_code,
            ),
        )
        cur.execute(
            """
            SELECT client_id, status
            FROM dbo.desktop_clients
            WHERE device_fingerprint = ?
            """,
            (payload.device_fingerprint.strip(),),
        )
        row = _row_to_dict(cur, cur.fetchone())
        conn.commit()
        return row
    finally:
        conn.close()


def get_config(client_id):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                c.client_id, c.status, c.tenant_id, c.store_id, c.store_code,
                c.store_name, c.server_base_url,
                cfg.latest_version, cfg.min_version, cfg.update_url,
                cfg.force_update, cfg.maintenance_message
            FROM dbo.desktop_clients c
            CROSS JOIN dbo.desktop_client_config cfg
            WHERE c.client_id = ?
            """,
            (client_id,),
        )
        row = _row_to_dict(cur, cur.fetchone())
        if row:
            row["force_update"] = bool(row.get("force_update"))
        return row
    finally:
        conn.close()


def heartbeat(client_id, app_version):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.desktop_clients
            SET last_seen_at = SYSUTCDATETIME(),
                app_version = COALESCE(?, app_version),
                updated_at = SYSUTCDATETIME()
            WHERE client_id = ?
            """,
            (app_version, client_id),
        )
        cur.execute(
            "SELECT client_id, status FROM dbo.desktop_clients WHERE client_id = ?",
            (client_id,),
        )
        row = _row_to_dict(cur, cur.fetchone())
        conn.commit()
        return row
    finally:
        conn.close()


def list_devices():
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                client_id, device_fingerprint, machine_name, app_version, status,
                tenant_id, store_id, store_code, store_name, server_base_url,
                enabled, requested_store_name, requested_store_code, install_code,
                last_seen_at, created_at, updated_at
            FROM dbo.desktop_clients
            ORDER BY created_at DESC
            """
        )
        return [_normalize_device(_row_to_dict(cur, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def approve_device(client_id, payload):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.desktop_clients
            SET tenant_id = ?,
                store_id = ?,
                store_code = ?,
                store_name = ?,
                server_base_url = ?,
                enabled = ?,
                status = CASE WHEN ? = 1 THEN 'approved' ELSE 'disabled' END,
                updated_at = SYSUTCDATETIME()
            WHERE client_id = ?
            """,
            (
                payload.tenant_id,
                payload.store_id,
                payload.store_code,
                payload.store_name,
                payload.server_base_url,
                1 if payload.enabled else 0,
                1 if payload.enabled else 0,
                client_id,
            ),
        )
        cur.execute(
            """
            SELECT
                client_id, device_fingerprint, machine_name, app_version, status,
                tenant_id, store_id, store_code, store_name, server_base_url,
                enabled, requested_store_name, requested_store_code, install_code,
                last_seen_at, created_at, updated_at
            FROM dbo.desktop_clients
            WHERE client_id = ?
            """,
            (client_id,),
        )
        row = _normalize_device(_row_to_dict(cur, cur.fetchone()))
        conn.commit()
        return row
    finally:
        conn.close()


def _normalize_device(row):
    if row:
        row["enabled"] = bool(row.get("enabled"))
    return row
