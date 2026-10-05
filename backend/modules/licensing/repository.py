from pathlib import Path
from threading import Lock

from config.database import get_connection as get_platform_connection
from modules.licensing.db_resolver import get_license_connection

_SQL_DIR = Path(__file__).with_name("sql")
_TENANTS_MIGRATION = _SQL_DIR / "0002_tenants_license_db_mode.sql"
_LICENSING_MIGRATION = _SQL_DIR / "0001_licensing.sql"

_schema_lock = Lock()
_platform_schema_ready = False
_license_schema_ready_targets = set()


def _run_script(conn, sql_file):
    cur = conn.cursor()
    script = sql_file.read_text(encoding="utf-8")
    for batch in (part.strip() for part in script.split("\nGO")):
        if batch:
            cur.execute(batch)
    conn.commit()


def _ensure_platform_schema():
    """dbo.tenants.license_db_mode etc - always lives on the shared platform
    DB regardless of any tenant's own license_db_mode choice. Also applies the
    licensing tables (tenant_licenses/audit/usage) to the platform DB itself,
    since that is where every SHARED-mode tenant's data lives (the default
    and common case) - this also guarantees the admin list/join query below
    always has those tables to query, even before any tenant ever checks in."""
    global _platform_schema_ready
    if _platform_schema_ready:
        return
    with _schema_lock:
        if _platform_schema_ready:
            return
        conn = get_platform_connection()
        try:
            _run_script(conn, _TENANTS_MIGRATION)
            _run_script(conn, _LICENSING_MIGRATION)
            _platform_schema_ready = True
            _license_schema_ready_targets.add("SHARED")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _license_target_key(tenant_id):
    conn = get_platform_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT license_db_mode, license_db_server, license_db_name FROM dbo.tenants WHERE tenant_id = ?",
            (tenant_id,),
        )
        row = cur.fetchone()
        if not row or (row[0] or "SHARED").upper() != "DEDICATED":
            return "SHARED"
        return f"DEDICATED::{row[1]}::{row[2]}"
    finally:
        conn.close()


def _get_tenant_license_connection(tenant_id):
    """Resolves the connection for tenant_id and ensures dbo.tenant_licenses /
    dbo.tenant_license_audit / dbo.tenant_usage_status exist on it."""
    _ensure_platform_schema()
    conn = get_license_connection(tenant_id)
    target = _license_target_key(tenant_id)
    if target not in _license_schema_ready_targets:
        with _schema_lock:
            if target not in _license_schema_ready_targets:
                try:
                    _run_script(conn, _LICENSING_MIGRATION)
                    _license_schema_ready_targets.add(target)
                except Exception:
                    conn.rollback()
                    raise
    return conn


def _rows_to_dicts(cursor):
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _insert_audit(cur, tenant_id, event_type, detail=None, actor=None):
    cur.execute(
        """
        INSERT INTO dbo.tenant_license_audit (tenant_id, event_type, detail, actor, created_at)
        VALUES (?, ?, ?, ?, SYSUTCDATETIME())
        """,
        (tenant_id, event_type, detail, actor),
    )


def resolve_tenant_id_for_store(store_id):
    conn = get_platform_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT tenant_id FROM dbo.stores WHERE store_id = ?", (store_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def start_trial(tenant_id, trial_days):
    conn = _get_tenant_license_connection(tenant_id)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            IF NOT EXISTS (SELECT 1 FROM dbo.tenant_licenses WHERE tenant_id = ?)
            INSERT INTO dbo.tenant_licenses
                (tenant_id, license_state, trial_days, trial_started_at, trial_ends_at)
            VALUES
                (?, 'trial_active', ?, SYSUTCDATETIME(), DATEADD(day, ?, SYSUTCDATETIME()))
            """,
            (tenant_id, tenant_id, trial_days, trial_days),
        )
        if cur.rowcount:
            _insert_audit(cur, tenant_id, "trial_started", f"{trial_days}-day trial")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_license_row(tenant_id):
    conn = _get_tenant_license_connection(tenant_id)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT tenant_id, license_state, trial_days, trial_started_at, trial_ends_at,
                   license_key, issued_at, issued_by, expires_at, revoked_at, revoked_by, notes
            FROM dbo.tenant_licenses
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        )
        rows = _rows_to_dicts(cur)
        return rows[0] if rows else None
    finally:
        conn.close()


def expire_trial_if_due(tenant_id):
    """Lazily flips trial_active -> trial_expired once trial_ends_at has
    passed. Called on every check-in so expiry takes effect without any
    background job."""
    conn = _get_tenant_license_connection(tenant_id)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.tenant_licenses
            SET license_state = 'trial_expired', updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ? AND license_state = 'trial_active'
              AND trial_ends_at <= SYSUTCDATETIME()
            """,
            (tenant_id,),
        )
        if cur.rowcount:
            _insert_audit(cur, tenant_id, "trial_expired", None, "SYSTEM")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def record_checkin(store_id, tenant_id, agent_version=None):
    """Upserts the SINGLE usage row for this store - never inserts a second
    row for the same store_id."""
    conn = _get_tenant_license_connection(tenant_id)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.tenant_usage_status
            SET last_active_date = CAST(SYSUTCDATETIME() AS DATE),
                last_active_time = CAST(SYSUTCDATETIME() AS TIME(0)),
                last_active_at = SYSUTCDATETIME(),
                agent_version = ?,
                updated_at = SYSUTCDATETIME()
            WHERE store_id = ?
            """,
            (agent_version, store_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO dbo.tenant_usage_status
                    (store_id, tenant_id, last_active_date, last_active_time, last_active_at, agent_version, updated_at)
                VALUES
                    (?, ?, CAST(SYSUTCDATETIME() AS DATE), CAST(SYSUTCDATETIME() AS TIME(0)), SYSUTCDATETIME(), ?, SYSUTCDATETIME())
                """,
                (store_id, tenant_id, agent_version),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def issue_key(tenant_id, license_key, issued_by, expires_at=None, notes=None):
    conn = _get_tenant_license_connection(tenant_id)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.tenant_licenses
            SET license_state = 'licensed', license_key = ?, issued_at = SYSUTCDATETIME(),
                issued_by = ?, expires_at = ?, revoked_at = NULL, revoked_by = NULL,
                notes = ?, updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ?
            """,
            (license_key, issued_by, expires_at, notes, tenant_id),
        )
        if not cur.rowcount:
            raise ValueError("Tenant has no license record - create the tenant first")
        _insert_audit(cur, tenant_id, "issued", notes, issued_by)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def revoke(tenant_id, revoked_by, notes=None):
    conn = _get_tenant_license_connection(tenant_id)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.tenant_licenses
            SET license_state = 'revoked', revoked_at = SYSUTCDATETIME(),
                revoked_by = ?, notes = ?, updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ?
            """,
            (revoked_by, notes, tenant_id),
        )
        if not cur.rowcount:
            raise ValueError("Tenant has no license record")
        _insert_audit(cur, tenant_id, "revoked", notes, revoked_by)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def renew(tenant_id, expires_at, issued_by):
    conn = _get_tenant_license_connection(tenant_id)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.tenant_licenses
            SET license_state = 'licensed', expires_at = ?, updated_at = SYSUTCDATETIME()
            WHERE tenant_id = ?
            """,
            (expires_at, tenant_id),
        )
        if not cur.rowcount:
            raise ValueError("Tenant has no license record")
        _insert_audit(cur, tenant_id, "renewed", f"expires_at={expires_at}", issued_by)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_db_mode(tenant_id, mode, server=None, database=None, username=None,
                 password_encrypted=None, driver=None):
    _ensure_platform_schema()
    conn = get_platform_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE dbo.tenants
            SET license_db_mode = ?, license_db_server = ?, license_db_name = ?,
                license_db_username = ?, license_db_password_encrypted = ?, license_db_driver = ?
            WHERE tenant_id = ?
            """,
            (mode, server, database, username, password_encrypted, driver, tenant_id),
        )
        if not cur.rowcount:
            raise ValueError("Tenant not found")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_tenants_with_status(tenant_id_filter=None):
    """Admin grid: license state joined with the single last-active row per
    store, aggregated to the most recent activity per tenant.

    Reads tenant_licenses/tenant_usage_status from the PLATFORM DB only, so a
    DEDICATED-mode tenant's real license_state/last_active_at (which live on
    its own database) won't show correctly here - use get_license_row /
    get_audit_log (tenant-scoped, DB-mode aware) for that tenant's detail view
    instead. Acceptable v1 limitation since dedicated DBs are the rare
    opt-in case, not the default."""
    _ensure_platform_schema()
    conn = get_platform_connection()
    try:
        cur = conn.cursor()
        where = "WHERE t.tenant_id = ?" if tenant_id_filter else ""
        params = (tenant_id_filter,) if tenant_id_filter else ()
        cur.execute(
            f"""
            SELECT
                CAST(t.tenant_id AS VARCHAR(36)) AS tenant_id,
                t.tenant_name,
                t.tenant_code,
                t.license_db_mode,
                tl.license_state,
                tl.trial_days,
                tl.trial_ends_at,
                tl.license_key,
                tl.issued_at,
                tl.expires_at,
                us.last_active_at
            FROM dbo.tenants t
            LEFT JOIN dbo.tenant_licenses tl ON tl.tenant_id = t.tenant_id
            LEFT JOIN (
                SELECT tenant_id, MAX(last_active_at) AS last_active_at
                FROM dbo.tenant_usage_status
                GROUP BY tenant_id
            ) us ON us.tenant_id = t.tenant_id
            {where}
            ORDER BY t.tenant_name
            """,
            params,
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()


def get_audit_log(tenant_id, limit=100):
    conn = _get_tenant_license_connection(tenant_id)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TOP (?) audit_id, event_type, detail, actor, created_at
            FROM dbo.tenant_license_audit
            WHERE tenant_id = ?
            ORDER BY created_at DESC, audit_id DESC
            """,
            (limit, tenant_id),
        )
        return _rows_to_dicts(cur)
    finally:
        conn.close()
