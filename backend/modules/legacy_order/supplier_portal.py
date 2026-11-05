"""Supplier ordering portals for the Procurement workspace's Sites panel.

Owner 2026-11-04: keep each supplier's portal address in a supplier table,
with its login at two levels (sql/0012):
  * SUPPLIER level -- dbo.SupplierPortal: the portal itself (name + address,
    the same for every store) and optionally ONE login all stores share. The
    portal row is the cross-store identity because a branch's SupplierCode
    differs per store (OrderSuppliers.CommonSupplierCode maps them).
  * STORE level -- dbo.SupplierPortalStore: which of this store's suppliers
    orders there (its UnifiedSupplierCODE, so Procurement opens the picked
    supplier's portal) and the store's own login, which wins over the
    supplier-level one.

Passwords are Fernet-encrypted with the platform key (as dbo.stores) and
never come back from list_portals -- only store_logins() returns them, for
the Stock Client's auto sign-in. Never log them.
"""
import os
import re
from pathlib import Path

import pyodbc
from cryptography.fernet import InvalidToken

from modules.legacy_order import database
from services.store_crypto_service import StoreCryptoService

# Same key as dbo.stores and the OrderNMC mirror targets (services/store_service.py).
_KEY_FILE = Path(__file__).resolve().parents[3] / "store_agent" / "config" / "fernet.key"
NAME_MAX, URL_MAX, USERNAME_MAX, PASSWORD_MAX = 100, 1000, 200, 200
_STORE_COLUMNS = ("SupplierCode", "SupplierName", "UserName", "PasswordEnc", "AutoSubmit")
_SCHEMA_READY = False


def _ensure_schema():
    """Apply sql/0012 once per process on its own connection (as
    supplier_whatsapp._ensure_schema)."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    path = os.path.join(os.path.dirname(__file__), "sql", "0012_supplier_portal.sql")
    with open(path, encoding="utf-8") as fh:
        script = fh.read()
    with database.get_central_connection() as conn:
        ddl = conn.cursor()
        for batch in [b.strip() for b in re.split(r"^\s*GO\s*$", script, flags=re.MULTILINE) if b.strip()]:
            ddl.execute(batch)
        conn.commit()
    _SCHEMA_READY = True


def _encrypt(password):
    return pyodbc.Binary(StoreCryptoService.encrypt_password(password, _KEY_FILE.read_bytes()))


def _decrypt(blob):
    """None when the value can't be read (another key): treated as no password."""
    try:
        return StoreCryptoService.decrypt_password(bytes(blob), _KEY_FILE.read_bytes())
    except (InvalidToken, TypeError, ValueError):
        return None


def clean_name(text):
    name = " ".join(str(text or "").split())
    if not name:
        raise ValueError("Enter the portal's name.")
    return name[:NAME_MAX]


def clean_url(text):
    """A web address only; https:// is assumed when the scheme is left out."""
    url = str(text or "").strip()
    if url and not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        url = f"https://{url}"
    if len(url) > URL_MAX or not re.match(r"^https?://[^\s/?#]+\S*$", url, re.I):
        raise ValueError("Enter the portal's web address, e.g. https://portal.example.com")
    return url


def _store(store_name):
    store = str(store_name or "").strip()
    if not store or len(store) > 50:
        raise ValueError("Pick a store first.")
    return store


def _login(username, has_password, auto_submit):
    """What a page may know about a login: never the password."""
    if not (username or has_password):
        return None
    return {"username": username or "", "has_password": bool(has_password), "auto_submit": bool(auto_submit)}


_LIST_SQL = (
    "SELECT p.PortalId, p.PortalName, p.PortalUrl, p.SortOrder, p.UserName, "
    "CAST(CASE WHEN p.PasswordEnc IS NULL THEN 0 ELSE 1 END AS BIT), p.AutoSubmit, "
    "s.SupplierCode, s.SupplierName, s.UserName, "
    "CAST(CASE WHEN s.PasswordEnc IS NULL THEN 0 ELSE 1 END AS BIT), s.AutoSubmit "
    "FROM dbo.SupplierPortal p "
    "LEFT JOIN dbo.SupplierPortalStore s ON s.PortalId = p.PortalId AND s.StoreName = ? "
)


def _row_to_portal(r):
    return {
        "portal_id": int(r[0]),
        "name": r[1],
        "url": r[2],
        "sort_order": int(r[3] or 0),
        "supplier_code": (r[7] or "").strip(),
        "supplier_name": (r[8] or "").strip(),
        "store_login": _login(r[9], r[10], r[6] if r[11] is None else r[11]),
        "supplier_login": _login(r[4], r[5], r[6]),
        # The login that signs this store in: its own, else the supplier's.
        "login_level": "store" if r[10] else ("supplier" if r[5] else None),
    }


def list_portals(store_name):
    """Every portal as this store sees it (store_name '' = no store's view)."""
    _ensure_schema()
    with database.get_central_connection() as conn:
        rows = conn.cursor().execute(_LIST_SQL + "ORDER BY p.SortOrder, p.PortalName", store_name or "").fetchall()
    return [_row_to_portal(r) for r in rows]


def get_portal(store_name, portal_id):
    _ensure_schema()
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(_LIST_SQL + "WHERE p.PortalId = ?", store_name or "", int(portal_id)).fetchone()
    return _row_to_portal(row) if row else None


def store_logins(store_name):
    """The login each portal signs this store in with -- the store's own,
    else the supplier-level one -- WITH its password, for the Stock Client's
    auto sign-in (which keeps them encrypted on the PC). Never log this."""
    _ensure_schema()
    with database.get_central_connection() as conn:
        rows = conn.cursor().execute(
            "SELECT p.PortalId, p.PortalUrl, p.UserName, p.PasswordEnc, p.AutoSubmit, "
            "s.UserName, s.PasswordEnc, s.AutoSubmit "
            "FROM dbo.SupplierPortal p "
            "LEFT JOIN dbo.SupplierPortalStore s ON s.PortalId = p.PortalId AND s.StoreName = ? "
            "WHERE p.PasswordEnc IS NOT NULL OR s.PasswordEnc IS NOT NULL "
            "ORDER BY p.SortOrder, p.PortalName",
            store_name or "",
        ).fetchall()
    items = []
    for r in rows:
        if r[6] is not None:
            level, username, blob, auto = "store", r[5], r[6], (r[4] if r[7] is None else r[7])
        else:
            level, username, blob, auto = "supplier", r[2], r[3], r[4]
        password = _decrypt(blob)
        if password is None:
            continue
        items.append({"portal_id": int(r[0]), "url": r[1], "username": username or "",
                      "password": password, "auto_submit": bool(auto), "level": level})
    return items


def _require_portal(cur, portal_id):
    if not cur.execute("SELECT 1 FROM dbo.SupplierPortal WHERE PortalId = ?", int(portal_id)).fetchone():
        raise LookupError("That portal no longer exists.")


def _login_user(username, password, has_saved):
    """Validated username for a login save (None when blank)."""
    username = str(username or "").strip()
    if len(username) > USERNAME_MAX or len(password or "") > PASSWORD_MAX:
        raise ValueError("That username or password is too long.")
    if not password and not has_saved:
        raise ValueError("Enter the password.")
    return username or None


def _set_clause(sets):
    """'Col = ?' per value, a literal NULL for None: pyodbc binds None as
    varchar, which a VARBINARY column rejects. Columns come from code only."""
    if not set(sets) <= set(_STORE_COLUMNS) | {"PortalName", "PortalUrl"}:
        raise ValueError("Unknown column.")
    clause = ", ".join(f"{col} = ?" if value is not None else f"{col} = NULL" for col, value in sets.items())
    return clause, [value for value in sets.values() if value is not None]


def _upsert_store_row(cur, store, portal_id, sets, actor):
    """Insert-or-update one store row. A row left with no supplier link and
    no login says nothing, so it is removed."""
    clause, values = _set_clause(sets)
    updated = cur.execute(
        f"UPDATE dbo.SupplierPortalStore SET {clause}, UpdatedBy = ?, UpdatedAt = GETDATE() "
        "WHERE StoreName = ? AND PortalId = ?",
        *values, actor, store, portal_id,
    ).rowcount
    if not updated:
        cols = [col for col, value in sets.items() if value is not None]
        cur.execute(
            f"INSERT INTO dbo.SupplierPortalStore ({''.join(c + ', ' for c in cols)}UpdatedBy, StoreName, PortalId) "
            f"VALUES ({''.join('?, ' for _ in cols)}?, ?, ?)",
            *values, actor, store, portal_id,
        )
    cur.execute(
        "DELETE FROM dbo.SupplierPortalStore WHERE StoreName = ? AND PortalId = ? "
        "AND SupplierCode IS NULL AND UserName IS NULL AND PasswordEnc IS NULL",
        store, portal_id,
    )


def create_portal(name, url, actor=None):
    """A new portal for every store, at the end of the list."""
    _ensure_schema()
    name, url = clean_name(name), clean_url(url)
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        if cur.execute("SELECT 1 FROM dbo.SupplierPortal WHERE PortalUrl = ?", url).fetchone():
            raise ValueError("That portal is already in the list.")
        portal_id = cur.execute(
            "INSERT INTO dbo.SupplierPortal (PortalName, PortalUrl, SortOrder, UpdatedBy) "
            "OUTPUT INSERTED.PortalId "
            "SELECT ?, ?, ISNULL(MAX(SortOrder), 0) + 1, ? FROM dbo.SupplierPortal",
            name, url, actor,
        ).fetchone()[0]
        conn.commit()
    return get_portal("", portal_id)


def update_portal(portal_id, name, url, actor=None):
    _ensure_schema()
    url = clean_url(url)
    clause, values = _set_clause({"PortalName": clean_name(name), "PortalUrl": url})
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        if cur.execute("SELECT 1 FROM dbo.SupplierPortal WHERE PortalUrl = ? AND PortalId <> ?", url, int(portal_id)).fetchone():
            raise ValueError("That portal is already in the list.")
        if not cur.execute(
            f"UPDATE dbo.SupplierPortal SET {clause}, UpdatedBy = ?, UpdatedAt = GETDATE() WHERE PortalId = ?",
            *values, actor, int(portal_id),
        ).rowcount:
            raise LookupError("That portal no longer exists.")
        conn.commit()
    return get_portal("", portal_id)


def delete_portal(portal_id):
    """The portal goes for every store, with each store's link and login."""
    _ensure_schema()
    with database.get_central_connection() as conn:
        deleted = conn.cursor().execute("DELETE FROM dbo.SupplierPortal WHERE PortalId = ?", int(portal_id)).rowcount
        conn.commit()
    if not deleted:
        raise LookupError("That portal no longer exists.")


def reorder_portals(portal_ids):
    """The Sites bar order, for every store: portal_ids first to last."""
    _ensure_schema()
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        for order, portal_id in enumerate([int(i) for i in portal_ids or []], start=1):
            cur.execute("UPDATE dbo.SupplierPortal SET SortOrder = ? WHERE PortalId = ?", order, portal_id)
        conn.commit()


def save_supplier_login(portal_id, username, password, auto_submit=True, clear=False, actor=None):
    """The supplier-level login: every store without its own signs in with
    it. A blank password keeps the saved one; clear removes the login."""
    _ensure_schema()
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT CASE WHEN PasswordEnc IS NULL THEN 0 ELSE 1 END FROM dbo.SupplierPortal WHERE PortalId = ?",
            int(portal_id),
        ).fetchone()
        if not row:
            raise LookupError("That portal no longer exists.")
        if clear:
            sets = {"UserName": None, "PasswordEnc": None}
        else:
            sets = {"UserName": _login_user(username, password, bool(row[0])), "AutoSubmit": 1 if auto_submit else 0}
            if password:
                sets["PasswordEnc"] = _encrypt(password)
        clause, values = _set_clause(sets)
        cur.execute(
            f"UPDATE dbo.SupplierPortal SET {clause}, UpdatedBy = ?, UpdatedAt = GETDATE() WHERE PortalId = ?",
            *values, actor, int(portal_id),
        )
        conn.commit()


def save_store_login(store_name, portal_id, username, password, auto_submit=True, clear=False, actor=None):
    """The store's own login for a portal; it wins over the supplier level."""
    _ensure_schema()
    store = _store(store_name)
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _require_portal(cur, portal_id)
        if clear:
            sets = {"UserName": None, "PasswordEnc": None, "AutoSubmit": None}
        else:
            saved = cur.execute(
                "SELECT 1 FROM dbo.SupplierPortalStore WHERE StoreName = ? AND PortalId = ? AND PasswordEnc IS NOT NULL",
                store, int(portal_id),
            ).fetchone()
            sets = {"UserName": _login_user(username, password, bool(saved)), "AutoSubmit": 1 if auto_submit else 0}
            if password:
                sets["PasswordEnc"] = _encrypt(password)
        _upsert_store_row(cur, store, int(portal_id), sets, actor)
        conn.commit()


def link_supplier(store_name, portal_id, supplier_code, supplier_name=None, actor=None):
    """Which of this store's suppliers orders on the portal (blank unlinks)."""
    _ensure_schema()
    store = _store(store_name)
    code = str(supplier_code or "").strip()
    if len(code) > 200:
        raise ValueError("That supplier code is too long.")
    name = " ".join(str(supplier_name or "").split())[:200] or None
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        _require_portal(cur, portal_id)
        _upsert_store_row(cur, store, int(portal_id),
                          {"SupplierCode": code or None, "SupplierName": name if code else None}, actor)
        conn.commit()
