from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    app_key: str = Field(..., max_length=40)
    action: str = Field(..., max_length=40)
    args: dict[str, Any] = Field(default_factory=dict)


class BulkCommandRequest(CommandRequest):
    device_ids: list[str] = Field(..., min_length=1, max_length=500)


class EnrollCodeRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=200)
    hours: int = 24
    max_uses: int = 1


class EnrollRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=20)
    device_fingerprint: str = Field(..., min_length=1, max_length=200)
    public_key: str = Field(..., min_length=1)
    machine_name: Optional[str] = Field(None, max_length=200)
    app_version: Optional[str] = Field(None, max_length=50)


class AppStatus(BaseModel):
    app_key: str
    installed: bool = False
    status: Optional[str] = None          # running | stopped | pending | not-installed | unknown
    version: Optional[str] = None
    desired_state: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


class HeartbeatRequest(BaseModel):
    hostname: Optional[str] = None
    local_ip: Optional[str] = None
    os_version: Optional[str] = None
    controller_version: Optional[str] = None
    ho_url: Optional[str] = None
    apps: list[AppStatus] = Field(default_factory=list)


class CommandResultRequest(BaseModel):
    status: str
    exit_code: Optional[int] = None
    result_text: Optional[str] = None


class TerminalOpenRequest(BaseModel):
    device_id: str


class TerminalInputRequest(BaseModel):
    data: str = Field(..., max_length=20000)


class TerminalOutputRequest(BaseModel):
    chunks: list[str] = Field(default_factory=list)
    closed: bool = False
    reason: Optional[str] = Field(None, max_length=200)
