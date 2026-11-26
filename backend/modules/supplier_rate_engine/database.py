"""Per-tenant SQL Server connections for the Supplier Rate Engine.

This engine reads PurchaseTrans-equivalent data from each tenant's OWN
purchase/order database (the same family of "legacy" databases --
OrderNMC / OrderSMS / OrderSuccess -- that modules.legacy_order.database
targets), which can live on a DIFFERENT SQL Server instance per HO than the
one this backend's own DB_* variables point at. SMS tenant data, for
example, was found on 192.168.10.32 (NODE9-PC\\SQLEXPRESS), a different host
than this repo's own DB_SERVER (192.168.10.73).

Rather than overload LEGACY_DB_* (shared with the Legacy Order console,
which assumes one server for all its tenants), tenant connection info here
is a small explicit lookup, configured per tenant via
SUPPLIER_RATE_ENGINE_TENANTS:

    SUPPLIER_RATE_ENGINE_TENANTS="SMS=192.168.10.32\\SQLEXPRESS,OrderSMS,sa,Admin123;NATHAN=192.168.10.73,NEXORA_PLATFORM,sa,Admin123"

Each entry is ``tenant_key=server,database,username,password``. tenant_key
is an engine-local short name (not necessarily the platform tenant_id GUID)
used by the API's ``tenant`` query/path parameter.
"""

import os

import pyodbc

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional / already loaded
    pass

_DEFAULT_DRIVER = "ODBC Driver 17 for SQL Server"


class SupplierRateEngineConfigError(RuntimeError):
    """A tenant was requested that has no connection configured."""


def _driver():
    return os.getenv("SUPPLIER_RATE_ENGINE_DRIVER") or os.getenv("DB_DRIVER") or _DEFAULT_DRIVER


def _parse_tenants():
    raw = os.getenv("SUPPLIER_RATE_ENGINE_TENANTS", "")
    out = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, rest = part.split("=", 1)
        fields = [f.strip() for f in rest.split(",")]
        if len(fields) != 4:
            continue
        server, database, username, password = fields
        out[key.strip().upper()] = {
            "server": server, "database": database, "username": username, "password": password,
        }
    return out


def known_tenants():
    """Engine-local tenant keys this backend is configured to reach."""
    return sorted(_parse_tenants().keys())


def _tenant_conf(tenant_key):
    return _parse_tenants().get(str(tenant_key or "").upper())


def connection_string(tenant_key):
    conf = _tenant_conf(tenant_key)
    if conf:
        return (
            f"DRIVER={{{_driver()}}};"
            f"SERVER={conf['server']};"
            f"DATABASE={conf['database']};"
            f"UID={conf['username']};"
            f"PWD={conf['password']};"
            "TrustServerCertificate=yes;"
        )
    # NATHAN is this backend's own platform DB (DB_SERVER/DB_DATABASE in
    # backend/.env) -- no separate SUPPLIER_RATE_ENGINE_TENANTS entry needed
    # unless Nathan's purchase data is ever moved off this instance.
    if str(tenant_key or "").upper() == "NATHAN":
        server = os.getenv("DB_SERVER", "192.168.10.73")
        database = os.getenv("DB_DATABASE", "NEXORA_PLATFORM")
        username = os.getenv("DB_USERNAME", "sa")
        password = os.getenv("DB_PASSWORD", "Admin123")
        return (
            f"DRIVER={{{_driver()}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
        )
    # SMS and Success share one SQL Server instance (192.168.10.32) but are
    # separate databases -- Success defaults alongside SMS so it works even
    # before an operator adds it to SUPPLIER_RATE_ENGINE_TENANTS explicitly.
    if str(tenant_key or "").upper() == "SUCCESS":
        sms_conf = _tenant_conf("SMS")
        server = sms_conf["server"] if sms_conf else "192.168.10.32\\SQLEXPRESS"
        username = sms_conf["username"] if sms_conf else "sa"
        password = sms_conf["password"] if sms_conf else "Admin123"
        return (
            f"DRIVER={{{_driver()}}};"
            f"SERVER={server};"
            f"DATABASE=OrderSuccess;"
            f"UID={username};"
            f"PWD={password};"
            "TrustServerCertificate=yes;"
        )
    raise SupplierRateEngineConfigError(
        f"No Supplier Rate Engine connection is configured for tenant '{tenant_key}'. "
        "Set SUPPLIER_RATE_ENGINE_TENANTS in backend/.env."
    )


def get_connection(tenant_key, timeout=15):
    """A fresh, read-only-by-convention connection to the given tenant's
    purchase/order database. No pooling -- same reasoning as
    config.database.get_connection: fail fast on a slow/unreachable server
    rather than pin a worker thread."""
    return pyodbc.connect(connection_string(tenant_key), timeout=timeout)
