"""Data access for supplier mail import.

Everything lives in NEXORA_PLATFORM: the tenant mailbox, the per-supplier
switch and the per-mail log. The supplier's mail id is its existing
sync.Suppliers.email (synced from the store ERP's supplier master); the
switch table can override it for a supplier whose master email is blank or
different. The switch is deliberately its own table, not columns on
sync.Suppliers, so the sync job can never overwrite it (same reasoning as
procurement/sql/0018_supplier_export_settings.sql).

has_mapping reads the active tenant's central legacy DB
(SupplierExcelMapping), so the caller sets legacy_database.set_active_tenant.
"""
import hashlib
import sys
from pathlib import Path

import pyodbc
from cryptography.fernet import Fernet, InvalidToken

from config.database import get_connection
from modules.legacy_order import database as legacy_database
from modules.procurement._dbutil import rows_to_dicts

# The mailbox password is Fernet-encrypted. Use the platform key (same as
# dbo.stores / supplier portal) where it exists; an exe HO node such as .32
# ships without it, so there a key of our own is generated once under the
# install's config folder (kept across backend updates). An existing own key
# always wins, so the choice never flips once a password is saved.
_SHARED_KEY = Path(__file__).resolve().parents[3] / "store_agent" / "config" / "fernet.key"
_CONFIG_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
               else Path(__file__).resolve().parents[2]) / "config"
_OWN_KEY = _CONFIG_DIR / "supplier_mail_import.key"


def _key():
    if _OWN_KEY.is_file():
        return _OWN_KEY.read_bytes().strip()
    if _SHARED_KEY.is_file():
        return _SHARED_KEY.read_bytes().strip()
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    _OWN_KEY.write_bytes(key)
    return key


def _encrypt(password):
    return pyodbc.Binary(Fernet(_key()).encrypt(password.encode("utf-8")))


def _decrypt(blob):
    """None when the value can't be read (another key): treated as no password."""
    try:
        return Fernet(_key()).decrypt(bytes(blob)).decode("utf-8")
    except (InvalidToken, TypeError, ValueError):
        return None

# Terminal statuses: the mail is done and is never read again.
DONE_STATUSES = ("IMPORTED", "SUPERSEDED", "NO_ATTACHMENT")
# A PROCESSING claim older than this is treated as abandoned (backend died).
STALE_CLAIM_MINUTES = 30

_PLATFORM_DDL = """
IF OBJECT_ID('dbo.supplier_mail_config', 'U') IS NULL
CREATE TABLE dbo.supplier_mail_config (
    tenant_id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY,
    is_enabled BIT NOT NULL DEFAULT 0,
    imap_host NVARCHAR(255) NULL,
    imap_port INT NULL,
    use_ssl BIT NOT NULL DEFAULT 1,
    username NVARCHAR(255) NULL,
    password_enc VARBINARY(MAX) NULL,
    folder NVARCHAR(255) NULL,
    poll_minutes INT NOT NULL DEFAULT 15,
    lookback_days INT NOT NULL DEFAULT 2,
    last_poll_at DATETIME NULL,
    last_poll_status VARCHAR(20) NULL,
    last_poll_message NVARCHAR(2000) NULL,
    updated_at DATETIME NULL,
    updated_by NVARCHAR(100) NULL
);
IF OBJECT_ID('dbo.supplier_mail_import_log', 'U') IS NULL
CREATE TABLE dbo.supplier_mail_import_log (
    log_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    dedup_key CHAR(64) NOT NULL CONSTRAINT UQ_supplier_mail_import_log UNIQUE,
    tenant_id UNIQUEIDENTIFIER NOT NULL,
    store_code NVARCHAR(50) NOT NULL,
    supplier_code NVARCHAR(200) NOT NULL,
    message_id NVARCHAR(500) NOT NULL,
    mail_from NVARCHAR(400) NULL,
    mail_subject NVARCHAR(1000) NULL,
    mail_date DATETIME NULL,
    attachment_name NVARCHAR(400) NULL,
    status VARCHAR(20) NOT NULL,
    rows_imported INT NULL,
    products_resolved INT NULL,
    message NVARCHAR(2000) NULL,
    created_at DATETIME NOT NULL DEFAULT GETDATE(),
    updated_at DATETIME NOT NULL DEFAULT GETDATE()
);
IF OBJECT_ID('dbo.supplier_mail_import_settings', 'U') IS NULL
CREATE TABLE dbo.supplier_mail_import_settings (
    tenant_id UNIQUEIDENTIFIER NOT NULL,
    store_id UNIQUEIDENTIFIER NOT NULL,
    supplier_code VARCHAR(100) NOT NULL,
    is_enabled BIT NOT NULL DEFAULT 0,
    mail_from NVARCHAR(500) NULL,
    subject_filter NVARCHAR(200) NULL,
    updated_at DATETIME NULL,
    updated_by NVARCHAR(100) NULL,
    CONSTRAINT PK_supplier_mail_import_settings PRIMARY KEY (tenant_id, store_id, supplier_code)
);
IF COL_LENGTH('dbo.supplier_mail_import_settings', 'all_stores') IS NULL
ALTER TABLE dbo.supplier_mail_import_settings ADD all_stores BIT NOT NULL
    CONSTRAINT DF_supplier_mail_import_settings_all_stores DEFAULT 0;
"""

_platform_ready = False


def _platform():
    global _platform_ready
    conn = get_connection()
    if not _platform_ready:
        conn.cursor().execute(_PLATFORM_DDL)
        conn.commit()
        _platform_ready = True
    return conn


# --- tenant mailbox -------------------------------------------------------

def get_config(tenant_id, with_password=False):
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT is_enabled, imap_host, imap_port, use_ssl, username, password_enc, folder, "
            "poll_minutes, lookback_days, last_poll_at, last_poll_status, last_poll_message, "
            "updated_at, updated_by FROM dbo.supplier_mail_config WHERE tenant_id = ?",
            (tenant_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    config = {
        "enabled": bool(row.is_enabled),
        "imap_host": row.imap_host or "",
        "imap_port": row.imap_port or 993,
        "use_ssl": bool(row.use_ssl),
        "username": row.username or "",
        "has_password": row.password_enc is not None,
        "folder": row.folder or "INBOX",
        "poll_minutes": row.poll_minutes,
        "lookback_days": row.lookback_days,
        "last_poll_at": row.last_poll_at.isoformat() if row.last_poll_at else None,
        "last_poll_status": row.last_poll_status,
        "last_poll_message": row.last_poll_message,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": row.updated_by,
    }
    if with_password:
        config["password"] = (_decrypt(row.password_enc) if row.password_enc is not None else None) or ""
    return config


def save_config(tenant_id, values, password=None, actor=None):
    """Upsert the tenant mailbox. A blank password keeps the saved one."""
    conn = _platform()
    try:
        cur = conn.cursor()
        params = (
            1 if values["enabled"] else 0, values["imap_host"], values["imap_port"],
            1 if values["use_ssl"] else 0, values["username"], values["folder"],
            values["poll_minutes"], values["lookback_days"], actor,
        )
        cur.execute(
            "UPDATE dbo.supplier_mail_config SET is_enabled = ?, imap_host = ?, imap_port = ?, "
            "use_ssl = ?, username = ?, folder = ?, poll_minutes = ?, lookback_days = ?, "
            "updated_at = GETDATE(), updated_by = ? WHERE tenant_id = ?",
            (*params, tenant_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO dbo.supplier_mail_config (is_enabled, imap_host, imap_port, use_ssl, "
                "username, folder, poll_minutes, lookback_days, updated_at, updated_by, tenant_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, GETDATE(), ?, ?)",
                (*params, tenant_id),
            )
        if password:
            cur.execute(
                "UPDATE dbo.supplier_mail_config SET password_enc = ? WHERE tenant_id = ?",
                (_encrypt(password), tenant_id),
            )
        conn.commit()
    finally:
        conn.close()


def record_poll(tenant_id, status, message):
    conn = _platform()
    try:
        conn.cursor().execute(
            "UPDATE dbo.supplier_mail_config SET last_poll_at = GETDATE(), last_poll_status = ?, "
            "last_poll_message = ? WHERE tenant_id = ?",
            (status, (message or "")[:2000], tenant_id),
        )
        conn.commit()
    finally:
        conn.close()


def due_tenants():
    """Enabled tenants whose poll interval has elapsed."""
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT CAST(c.tenant_id AS VARCHAR(36)) FROM dbo.supplier_mail_config c "
            "JOIN dbo.tenants t ON t.tenant_id = c.tenant_id AND t.is_active = 1 "
            "WHERE c.is_enabled = 1 AND (c.last_poll_at IS NULL "
            "OR DATEDIFF(MINUTE, c.last_poll_at, GETDATE()) >= c.poll_minutes)"
        )
        return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


# --- per-supplier switch ------------------------------------------------------

def list_suppliers(tenant_id, store_id):
    """Every active supplier of the store with its mail-import switch.
    master_email = sync.Suppliers.email; mail_from = the override (blank =
    use master_email)."""
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT RTRIM(CAST(s.suppliercode AS VARCHAR(100))) AS supplier_code, "
            "RTRIM(ISNULL(s.suppliername, '')) AS supplier_name, "
            "LTRIM(RTRIM(ISNULL(s.email, ''))) AS master_email, "
            "ISNULL(m.mail_from, '') AS mail_from, ISNULL(m.subject_filter, '') AS subject_filter, "
            "CAST(ISNULL(m.is_enabled, 0) AS BIT) AS enabled, CAST(ISNULL(m.all_stores, 0) AS BIT) AS all_stores "
            "FROM sync.Suppliers s "
            "LEFT JOIN dbo.supplier_mail_import_settings m ON m.tenant_id = s.tenant_id "
            "  AND m.store_id = s.store_id AND m.supplier_code = RTRIM(CAST(s.suppliercode AS VARCHAR(100))) "
            "WHERE s.tenant_id = ? AND s.store_id = ? AND ISNULL(s.isActive, 1) = 1 "
            "ORDER BY CASE WHEN m.is_enabled = 1 THEN 0 ELSE 1 END, RTRIM(s.suppliername)",
            (tenant_id, store_id),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def mapped_supplier_codes(store_code):
    """Supplier codes with a saved Excel column mapping for the store, from
    the ACTIVE tenant's central legacy DB."""
    with legacy_database.get_central_connection() as conn:
        rows = conn.cursor().execute(
            "SELECT DISTINCT RTRIM(SupplierCode) FROM SupplierExcelMapping WHERE StoreName = ?",
            (store_code,),
        ).fetchall()
    return {str(r[0]).strip() for r in rows if r[0]}


def enabled_suppliers(tenant_id):
    """Every switched-on supplier of the tenant with its effective mail id."""
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT CAST(m.store_id AS VARCHAR(36)) AS store_id, RTRIM(st.store_code) AS store_code, "
            "m.supplier_code, RTRIM(ISNULL(s.suppliername, '')) AS supplier_name, "
            "COALESCE(NULLIF(LTRIM(RTRIM(m.mail_from)), ''), LTRIM(RTRIM(ISNULL(s.email, '')))) AS mail_from, "
            "ISNULL(m.subject_filter, '') AS subject_filter, CAST(m.all_stores AS BIT) AS all_stores "
            "FROM dbo.supplier_mail_import_settings m "
            "JOIN dbo.stores st ON st.store_id = m.store_id AND ISNULL(st.is_active, 1) = 1 "
            "LEFT JOIN sync.Suppliers s ON s.tenant_id = m.tenant_id AND s.store_id = m.store_id "
            "  AND RTRIM(CAST(s.suppliercode AS VARCHAR(100))) = m.supplier_code "
            "WHERE m.tenant_id = ? AND m.is_enabled = 1",
            (tenant_id,),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def save_supplier(tenant_id, store_id, supplier_code, enabled, mail_from, subject_filter, all_stores=False, actor=None):
    conn = _platform()
    try:
        cur = conn.cursor()
        params = (1 if enabled else 0, mail_from or None, subject_filter or None, 1 if all_stores else 0, actor)
        cur.execute(
            "UPDATE dbo.supplier_mail_import_settings SET is_enabled = ?, mail_from = ?, subject_filter = ?, "
            "all_stores = ?, updated_at = GETDATE(), updated_by = ? "
            "WHERE tenant_id = ? AND store_id = ? AND supplier_code = ?",
            (*params, tenant_id, store_id, supplier_code),
        )
        if cur.rowcount == 0:
            cur.execute(
                "INSERT INTO dbo.supplier_mail_import_settings (is_enabled, mail_from, subject_filter, "
                "all_stores, updated_at, updated_by, tenant_id, store_id, supplier_code) "
                "VALUES (?, ?, ?, ?, GETDATE(), ?, ?, ?, ?)",
                (*params, tenant_id, store_id, supplier_code),
            )
        conn.commit()
    finally:
        conn.close()


def supplier_exists(tenant_id, store_id, supplier_code):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 1 1 FROM sync.Suppliers WHERE tenant_id = ? AND store_id = ? "
            "AND RTRIM(CAST(suppliercode AS VARCHAR(100))) = ?",
            (tenant_id, store_id, supplier_code),
        )
        return cur.fetchone() is not None
    finally:
        conn.close()


# --- per-mail log ------------------------------------------------------------

def dedup_key(tenant_id, store_code, supplier_code, message_id):
    raw = "\x1f".join(str(v).strip().lower() for v in (tenant_id, store_code, supplier_code, message_id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def statuses(keys):
    """{dedup_key: status} for already-logged mails."""
    if not keys:
        return {}
    conn = _platform()
    try:
        cur = conn.cursor()
        found = {}
        keys = list(keys)
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            cur.execute(
                f"SELECT dedup_key, status FROM dbo.supplier_mail_import_log "
                f"WHERE dedup_key IN ({', '.join('?' for _ in chunk)})",
                tuple(chunk),
            )
            found.update({row[0]: row[1] for row in cur.fetchall()})
        return found
    finally:
        conn.close()


def claim(key, tenant_id, store_code, supplier_code, mail):
    """Mark the mail PROCESSING. False when another worker holds it or it is
    already done -- so two backends polling the same mailbox never import
    the same mail twice."""
    conn = _platform()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO dbo.supplier_mail_import_log (dedup_key, tenant_id, store_code, supplier_code, "
                "message_id, mail_from, mail_subject, mail_date, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PROCESSING')",
                (key, tenant_id, store_code, supplier_code, mail["message_id"][:500],
                 (mail.get("from") or "")[:400], (mail.get("subject") or "")[:1000], mail.get("date")),
            )
            conn.commit()
            return True
        except pyodbc.IntegrityError:
            conn.rollback()
        done = ", ".join(f"'{s}'" for s in DONE_STATUSES)
        cur.execute(
            "UPDATE dbo.supplier_mail_import_log SET status = 'PROCESSING', updated_at = GETDATE() "
            f"WHERE dedup_key = ? AND status NOT IN ({done}) "
            "AND (status <> 'PROCESSING' OR DATEDIFF(MINUTE, updated_at, GETDATE()) >= ?)",
            (key, STALE_CLAIM_MINUTES),
        )
        claimed = cur.rowcount == 1
        conn.commit()
        return claimed
    finally:
        conn.close()


def finish(key, status, message=None, attachment_name=None, rows_imported=None, products_resolved=None):
    conn = _platform()
    try:
        conn.cursor().execute(
            "UPDATE dbo.supplier_mail_import_log SET status = ?, message = ?, attachment_name = ?, "
            "rows_imported = ?, products_resolved = ?, updated_at = GETDATE() WHERE dedup_key = ?",
            (status, (message or "")[:2000] or None, (attachment_name or "")[:400] or None,
             rows_imported, products_resolved, key),
        )
        conn.commit()
    finally:
        conn.close()


def supersede(key, tenant_id, store_code, supplier_code, mail):
    """Log an older, never-imported mail as SUPERSEDED by a newer import."""
    if claim(key, tenant_id, store_code, supplier_code, mail):
        finish(key, "SUPERSEDED", "A newer stock mail from this supplier was imported.")


def list_log(tenant_id, store_code=None, supplier_code=None, limit=100):
    where, params = ["tenant_id = ?"], [tenant_id]
    if store_code:
        where.append("store_code = ?")
        params.append(store_code)
    if supplier_code:
        where.append("supplier_code = ?")
        params.append(supplier_code)
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT TOP {int(limit)} log_id, store_code, supplier_code, mail_from, mail_subject, mail_date, "
            "attachment_name, status, rows_imported, products_resolved, message, created_at, updated_at "
            f"FROM dbo.supplier_mail_import_log WHERE {' AND '.join(where)} "
            "ORDER BY updated_at DESC, log_id DESC",
            tuple(params),
        )
        return rows_to_dicts(cur)
    finally:
        conn.close()


def latest_by_supplier(tenant_id, store_code):
    """{supplier_code: newest log row} for the supplier settings list."""
    conn = _platform()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT supplier_code, status, message, mail_date, updated_at FROM ("
            "  SELECT supplier_code, status, message, mail_date, updated_at, ROW_NUMBER() OVER ("
            "    PARTITION BY supplier_code ORDER BY CASE WHEN status = 'SUPERSEDED' THEN 1 ELSE 0 END, "
            "    updated_at DESC) AS rn"
            "  FROM dbo.supplier_mail_import_log WHERE tenant_id = ? AND store_code = ?"
            ") x WHERE rn = 1",
            (tenant_id, store_code),
        )
        return {str(row["supplier_code"]).strip(): row for row in rows_to_dicts(cur)}
    finally:
        conn.close()
