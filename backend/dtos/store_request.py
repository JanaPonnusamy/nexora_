
from __future__ import annotations

from pydantic import BaseModel

class StoreRequest(BaseModel):
    tenant_id: str
    store_code: str
    store_name: str
    server_name: str | None = None
    database_name: str | None = None

class StoreStatusRequest(BaseModel):
    is_active: bool


class StoreCredentialRequest(BaseModel):
    """Store DB connection credentials, edited from the HO UI and written to
    dbo.stores. password is optional: omit/blank it to change server/username
    without re-typing the password (the stored password_encrypted is kept)."""
    server_name: str | None = None
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    connection_type: str | None = None
