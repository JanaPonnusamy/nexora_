from typing import List, Optional

from pydantic import BaseModel

_VALID_STATES = {"RUNNING", "STOPPED"}


class HeartbeatRequest(BaseModel):
    store_id: str
    watchdog_version: Optional[str] = None
    installed_agent_version: Optional[str] = None
    service_state: Optional[str] = None
    last_action: Optional[str] = None


class SetStateRequest(BaseModel):
    desired_state: str


class BulkStateRequest(BaseModel):
    store_ids: List[str]
    desired_state: str


class SetVersionRequest(BaseModel):
    desired_version: Optional[str] = None


class BulkVersionRequest(BaseModel):
    store_ids: List[str]
    desired_version: Optional[str] = None
