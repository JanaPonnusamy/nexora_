from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CheckinRequest(BaseModel):
    store_id: str
    agent_version: Optional[str] = None


class IssueKeyRequest(BaseModel):
    license_key: str
    expires_at: Optional[datetime] = None
    notes: Optional[str] = None


class RevokeRequest(BaseModel):
    notes: Optional[str] = None


class RenewRequest(BaseModel):
    expires_at: Optional[datetime] = None


class SetDbModeRequest(BaseModel):
    mode: str  # SHARED | DEDICATED
    server: Optional[str] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # plaintext in, encrypted before storage
    driver: Optional[str] = None
