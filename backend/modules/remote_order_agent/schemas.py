"""Request/response models for the Remote Order Agent contract (/api/nmv/v1).

Shapes mirror ``remote_order_agent/docs/02_HO_API_Contract.md`` exactly. Models
are permissive on input (optional metadata the agent may or may not send) and
strict on the few fields HO acts on. Union syntax relies on
``from __future__ import annotations`` so this parses under pydantic v1 and v2.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---- 1. enrollment --------------------------------------------------------

class RegisterRequest(BaseModel):
    """POST /agent/register -- no bearer; the one-time code authorises it."""

    store_code: str = Field(..., min_length=1, max_length=50)
    store_id: str = Field(..., min_length=1, max_length=64)
    enrollment_code: str = Field(..., min_length=1, max_length=200)
    machine_name: str | None = Field(None, max_length=200)
    agent_version: str | None = Field(None, max_length=50)


# ---- 2. heartbeat ---------------------------------------------------------

class HeartbeatRequest(BaseModel):
    device_id: str | None = Field(None, max_length=64)
    agent_version: str | None = Field(None, max_length=50)
    queue: dict[str, Any] | None = None
    last_success: dict[str, Any] | None = None
    current_order_id: int | None = None


# ---- 3. order acknowledgement ---------------------------------------------

class OrderAckRequest(BaseModel):
    order_id: int
    version: int = 1
    state: str = Field(..., min_length=1, max_length=20)  # APPLIED|REJECTED|DEFERRED
    payload_sha256: str | None = Field(None, max_length=64)
    applied_line_count: int | None = None
    reason_code: str | None = Field(None, max_length=50)
    reason: str | None = Field(None, max_length=500)
    applied_at: str | None = Field(None, max_length=50)


# ---- 4. order result push -------------------------------------------------

class OrderResultItem(BaseModel):
    change_id: int
    operation: str = Field("U", max_length=1)  # I | U | D
    captured_at: str | None = Field(None, max_length=50)
    order_id: int
    product_code: Any
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    db_login: str | None = Field(None, max_length=200)
    host_name: str | None = Field(None, max_length=200)
    app_name: str | None = Field(None, max_length=200)


class OrderResultsRequest(BaseModel):
    batch_id: str = Field(..., min_length=1, max_length=64)
    queue_epoch: str = Field(..., min_length=1, max_length=64)
    count: int | None = None
    items_sha256: str | None = Field(None, max_length=64)
    items: list[OrderResultItem] = Field(default_factory=list)
