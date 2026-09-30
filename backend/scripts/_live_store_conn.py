"""Direct connection helper for a store's OWN live SQL Server (not OrderNMC,
not NEXORA_PLATFORM). Credentials come from NEXORA_PLATFORM.dbo.stores
(server_name/database_name/username/password_encrypted), decrypted with the
same Fernet key the store_agent modules already use.
"""
import sys
from pathlib import Path

import pyodbc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from repositories.store_repository import StoreRepository
from services.store_crypto_service import StoreCryptoService

_KEY_FILE = Path(__file__).resolve().parents[2] / "store_agent" / "config" / "fernet.key"

STORE_IDS = {
    "NMW": "DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0",
    "NMA": "109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1",
    "NMC": "FCBE8B35-B1A1-463E-80C6-73161CDC8F32",
}


def connect(store_code, timeout=15):
    store_id = STORE_IDS[store_code]
    row = StoreRepository().get_agent_config(store_id)
    if not row:
        raise ValueError(f"Store {store_code} not found in dbo.stores")
    _, _, server_name, database_name, username, password_encrypted, _, _, is_active = row
    if not is_active:
        raise ValueError(f"Store {store_code} is marked inactive")

    key = _KEY_FILE.read_bytes()
    password = StoreCryptoService.decrypt_password(password_encrypted, key)

    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={server_name};DATABASE={database_name};UID={username};PWD={password};"
        "TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str, timeout=timeout)
