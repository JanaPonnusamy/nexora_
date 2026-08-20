from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class AuditImmutableError(RuntimeError):
    """Raised when an update, delete, upsert, or mutation is attempted on an audit log row."""
    pass


class ActorRole(str, Enum):
    ADMIN = "admin"
    CUSTOMER = "customer"
    SYSTEM = "system"


class AuditStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class AuditCategory(str, Enum):
    AUTH = "auth"
    USER = "user"
    ROLE = "role"
    TENANT = "tenant"
    STORE = "store"
    MODULE = "module"
    SYNC = "sync"
    PROCUREMENT = "procurement"
    INVENTORY = "inventory"
    SYSTEM = "system"
    AUDIT = "audit"


class AuditEntry(BaseModel):
    log_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: ActorRole = ActorRole.SYSTEM
    actor_email: Optional[str] = None
    actor_name: Optional[str] = None
    action: str = Field(..., max_length=64)
    category: str = Field(..., max_length=30)
    target_type: Optional[str] = Field(None, max_length=64)
    target_id: Optional[str] = Field(None, max_length=255)
    target_label: Optional[str] = Field(None, max_length=255)
    reason: Optional[str] = Field(None, max_length=500)
    metadata: Optional[str] = None  # JSON string
    ip: Optional[str] = Field(None, max_length=45)
    user_agent: Optional[str] = Field(None, max_length=512)
    device: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=2)
    status: AuditStatus = AuditStatus.SUCCESS
    error_message: Optional[str] = Field(None, max_length=500)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AuditFilterParams(BaseModel):
    search: Optional[str] = None
    action: Optional[str] = None
    category: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    status: Optional[str] = None
    from_date: Optional[str] = None  # YYYY-MM-DD or ISO
    to_date: Optional[str] = None    # YYYY-MM-DD or ISO
    page: int = 1
    page_size: int = 25


class AuditActorOption(BaseModel):
    actor_id: str
    actor_name: Optional[str] = None
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None


class AuditFilterOptionsResponse(BaseModel):
    actors: list[AuditActorOption]
    actions: list[str]
    categories: list[str]
    target_types: list[str]
    statuses: list[str]
    actor_roles: list[str]


class AuditListResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int
