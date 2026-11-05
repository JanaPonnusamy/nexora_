"""Per-supplier web-order portal, stored on the supplier row.

Owner 2026-11-05 (simplified from the earlier shared-portal tables): each
supplier has its OWN ordering site and login -- nothing is shared across
suppliers or stores. So the portal lives as columns on dbo.OrderSuppliers
(keyed by UnifiedSupplierCODE + StoreName, the same key Procurement's By
Supplier screen uses):

  * PortalUrl         -- the supplier's ordering site
  * PortalUserName    -- the login username
  * PortalPasswordEnc -- the password, Fernet-encrypted with the platform key
                         (as dbo.stores); never stored or returned in plain text
  * PortalAutoSubmit  -- submit the login form automatically

The columns are added once by sync_engine._ensure_supplier_portal_columns and
carried to the remote OrderNMC DBs by the mirror. When a store order selects a
supplier and clicks Website, the client reads this row and signs in.
"""
import re
from pathlib import Path

import pyodbc
from cryptography.fernet import InvalidToken

from modules.legacy_order import database
from services.store_crypto_service import StoreCryptoService

# Same key as dbo.stores and the OrderNMC mirror targets.
_KEY_FILE = Path(__file__).resolve().parents[3] / "store_agent" / "config" / "fernet.key"
URL_MAX, USERNAME_MAX, PASSWORD_MAX = 1000, 200, 200


def _encrypt(password):
    return pyodbc.Binary(StoreCryptoService.encrypt_password(password, _KEY_FILE.read_bytes()))


def _decrypt(blob):
    """None when the value can't be read (another key): treated as no password."""
    try:
        return StoreCryptoService.decrypt_password(bytes(blob), _KEY_FILE.read_bytes())
    except (InvalidToken, TypeError, ValueError):
        return None


def _store(store_name):
    store = str(store_name or "").strip()
    if not store or len(store) > 50:
        raise ValueError("Pick a store first.")
    return store


def _code(supplier_code):
    code = str(supplier_code or "").strip()
    if not code or len(code) > 200:
        raise ValueError("Pick a supplier first.")
    return code


def clean_url(text):
    """A web address only; https:// is assumed when the scheme is left out.
    Blank is allowed -- it clears the portal."""
    url = str(text or "").strip()
    if not url:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        url = f"https://{url}"
    if len(url) > URL_MAX or not re.match(r"^https?://[^\s/?#]+\S*$", url, re.I):
        raise ValueError("Enter the portal's web address, e.g. https://portal.example.com")
    return url


# UnifiedSupplierCODE is the code the By Supplier screen passes; fall back to
# suppliercode for rows that never got a unified code stamped.
_WHERE = "storename = ? AND (UnifiedSupplierCODE = ? OR suppliercode = ?)"


def get_portal(store_name, supplier_code):
    """The supplier's portal as a page may see it -- never the password."""
    store, code = _store(store_name), _code(supplier_code)
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT TOP 1 PortalUrl, PortalUserName, "
            "CAST(CASE WHEN PortalPasswordEnc IS NULL THEN 0 ELSE 1 END AS BIT), PortalAutoSubmit "
            f"FROM dbo.OrderSuppliers WHERE {_WHERE}", store, code, code,
        ).fetchone()
    if not row:
        return None
    url = (row[0] or "").strip()
    return {
        "url": url,
        "username": (row[1] or "").strip(),
        "has_password": bool(row[2]),
        "auto_submit": True if row[3] is None else bool(row[3]),
        # A supplier's Website option is enabled only when a URL is configured.
        "enabled": bool(url),
    }


def get_login(store_name, supplier_code):
    """The portal login WITH its password, for the Stock Client's auto
    sign-in (which keeps it encrypted on the PC). Never log this. None when no
    URL or no readable password is set."""
    store, code = _store(store_name), _code(supplier_code)
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(
            "SELECT TOP 1 PortalUrl, PortalUserName, PortalPasswordEnc, PortalAutoSubmit "
            f"FROM dbo.OrderSuppliers WHERE {_WHERE}", store, code, code,
        ).fetchone()
    if not row or not (row[0] or "").strip():
        return None
    password = _decrypt(row[2]) if row[2] is not None else None
    return {
        "url": row[0].strip(),
        "username": (row[1] or "").strip(),
        "password": password or "",
        "auto_submit": True if row[3] is None else bool(row[3]),
    }


def save_portal(store_name, supplier_code, url, username, password, auto_submit=True, clear=False, actor=None):
    """Set (or clear) the supplier's portal URL + login. A blank password keeps
    the saved one; clear wipes the whole portal. actor is accepted for symmetry
    with the other writers (OrderSuppliers has no audit columns)."""
    store, code = _store(store_name), _code(supplier_code)
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        if not cur.execute(f"SELECT TOP 1 1 FROM dbo.OrderSuppliers WHERE {_WHERE}", store, code, code).fetchone():
            raise LookupError("That supplier is not in this store's list.")
        if clear:
            cur.execute(
                "UPDATE dbo.OrderSuppliers SET PortalUrl = NULL, PortalUserName = NULL, "
                f"PortalPasswordEnc = NULL, PortalAutoSubmit = NULL WHERE {_WHERE}",
                store, code, code,
            )
            conn.commit()
            return get_portal(store, code)

        clean = clean_url(url)
        username = str(username or "").strip()
        if len(username) > USERNAME_MAX or len(password or "") > PASSWORD_MAX:
            raise ValueError("That username or password is too long.")
        sets = ["PortalUrl = ?", "PortalUserName = ?", "PortalAutoSubmit = ?"]
        vals = [clean or None, username or None, 1 if auto_submit else 0]
        if password:
            sets.append("PortalPasswordEnc = ?")
            vals.append(_encrypt(password))
        elif not clean:
            # URL cleared without a new password: drop the stored password too.
            sets.append("PortalPasswordEnc = NULL")
        cur.execute(
            f"UPDATE dbo.OrderSuppliers SET {', '.join(sets)} WHERE {_WHERE}",
            *vals, store, code, code,
        )
        conn.commit()
    return get_portal(store, code)
