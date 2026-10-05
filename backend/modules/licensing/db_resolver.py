"""Resolves which database a given tenant's licensing/usage data lives in.

Default: the shared NEXORA_PLATFORM connection (config.database.get_connection),
same as every other module. A tenant can instead be pointed at a separate
dedicated database (dbo.tenants.license_db_mode = 'DEDICATED') for isolation -
in that case this module builds its own pyodbc connection from the
license_db_* columns on dbo.tenants, decrypting the password with the same
Fernet key/service the store connections already use (see
backend/scripts/_live_store_conn.py for the precedent).

dbo.tenants itself (including the license_db_mode column) ALWAYS lives in the
shared platform DB - only a tenant's tenant_licenses / tenant_license_audit /
tenant_usage_status rows move to the dedicated DB. Every function in
licensing/repository.py must call get_license_connection(tenant_id) instead
of importing config.database.get_connection directly - that is a deliberate
exception to the normal pattern used by every other module, made necessary by
the per-tenant DB choice requirement.
"""
from pathlib import Path

import pyodbc

from config.database import get_connection as get_platform_connection
from services.store_crypto_service import StoreCryptoService

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"
_KEY_FILE = Path(__file__).resolve().parents[3] / "store_agent" / "config" / "fernet.key"


def _load_tenant_db_mode(tenant_id):
    conn = get_platform_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT license_db_mode, license_db_server, license_db_name,
                   license_db_username, license_db_password_encrypted, license_db_driver
            FROM dbo.tenants
            WHERE tenant_id = ?
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "license_db_mode": row[0],
            "license_db_server": row[1],
            "license_db_name": row[2],
            "license_db_username": row[3],
            "license_db_password_encrypted": row[4],
            "license_db_driver": row[5],
        }
    finally:
        conn.close()


def _connect_dedicated(cfg):
    key = _KEY_FILE.read_bytes()
    password = StoreCryptoService.decrypt_password(cfg["license_db_password_encrypted"], key)
    driver = cfg["license_db_driver"] or _DEFAULT_DRIVER
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={cfg['license_db_server']};"
        f"DATABASE={cfg['license_db_name']};"
        f"UID={cfg['license_db_username']};PWD={password};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=10)


def encrypt_license_db_password(password):
    key = _KEY_FILE.read_bytes()
    return StoreCryptoService.encrypt_password(password, key)


def get_license_connection(tenant_id):
    """Return a live DB connection for tenant_id's licensing/usage data.
    Caller is responsible for closing it, same contract as get_connection()."""
    cfg = _load_tenant_db_mode(tenant_id)
    if not cfg or (cfg["license_db_mode"] or "SHARED").upper() != "DEDICATED":
        return get_platform_connection()
    return _connect_dedicated(cfg)
