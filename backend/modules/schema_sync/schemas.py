"""Request/response shapes for the Schema Sync (Dev -> Production) tool."""

from typing import List, Optional

from pydantic import BaseModel, Field


class ConnectionInput(BaseModel):
    host: str = Field(..., min_length=1, max_length=200)
    port: int = Field(1433, ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=128)
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=0, max_length=256)
    driver: Optional[str] = None


class TestConnectionRequest(BaseModel):
    connection: ConnectionInput


class TestConnectionResult(BaseModel):
    ok: bool
    database_exists: bool = False
    message: str = ""
    server_version: Optional[str] = None


class EnsureDatabaseRequest(BaseModel):
    connection: ConnectionInput


class EnsureDatabaseResult(BaseModel):
    ok: bool
    created: bool = False
    message: str = ""


class CompareRequest(BaseModel):
    source: ConnectionInput  # Dev - read-only
    target: ConnectionInput  # Production / HO - gets updated


class DiffItem(BaseModel):
    category: str
    schema_name: str
    object_name: str
    detail: str
    severity: str = "info"  # info | warn | destructive-skipped


class PlannedStatement(BaseModel):
    seq: int
    category: str
    schema_name: str
    object_name: str
    description: str
    sql: str


class CompareResult(BaseModel):
    generated_at: str
    tables_missing_in_target: List[DiffItem] = []
    tables_only_in_target: List[DiffItem] = []
    tables_skipped_as_artifacts: List[DiffItem] = []
    column_diffs: List[DiffItem] = []
    index_diffs: List[DiffItem] = []
    constraint_diffs: List[DiffItem] = []
    programmable_diffs: List[DiffItem] = []
    statements: List[PlannedStatement] = []
    summary: dict = {}


class ApplyRequest(BaseModel):
    target: ConnectionInput
    statements: List[PlannedStatement]


class ApplyResultItem(BaseModel):
    seq: int
    category: str
    object_name: str
    ok: bool
    message: str = ""


class ApplyResult(BaseModel):
    ok: bool
    applied: int
    failed: int
    results: List[ApplyResultItem] = []
