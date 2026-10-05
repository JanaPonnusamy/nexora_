"""Schema Sync API - Dev -> Production schema comparison and apply.

Platform-ops tool: connects to two SQL Server instances supplied at request
time (Dev is read-only source, Production/HO is the target that gets
updated). Restricted to super admin / platform users only.
"""
from fastapi import APIRouter, Depends

from dependencies.store_scope import require_super_admin
from modules.schema_sync import service
from modules.schema_sync.repository import ensure_database, local_connection_from_env, test_connection
from modules.schema_sync.schemas import (
    ApplyRequest,
    ApplyResult,
    CompareRequest,
    CompareResult,
    EnsureDatabaseRequest,
    EnsureDatabaseResult,
    LocalSourceInfo,
    TestConnectionRequest,
    TestConnectionResult,
)

router = APIRouter(prefix="/api/schema-sync", tags=["Schema Sync"])


@router.get("/local-source-info", response_model=LocalSourceInfo)
def local_source_info_endpoint(_: dict = Depends(require_super_admin)):
    """This server's own configured database - shown read-only in the UI so
    the operator doesn't need to know/re-type its host/db/username to use it
    as Source. Password is never returned to the client."""
    conn = local_connection_from_env()
    return LocalSourceInfo(host=conn["host"], port=conn["port"], database=conn["database"], username=conn["username"])


@router.post("/test-connection", response_model=TestConnectionResult)
def test_connection_endpoint(payload: TestConnectionRequest, _: dict = Depends(require_super_admin)):
    return test_connection(payload.connection.model_dump())


@router.post("/ensure-database", response_model=EnsureDatabaseResult)
def ensure_database_endpoint(payload: EnsureDatabaseRequest, _: dict = Depends(require_super_admin)):
    return ensure_database(payload.connection.model_dump())


@router.post("/compare", response_model=CompareResult)
def compare_endpoint(payload: CompareRequest, _: dict = Depends(require_super_admin)):
    source = payload.source.model_dump() if payload.source else local_connection_from_env()
    return service.compare(source, payload.target.model_dump())


@router.post("/apply", response_model=ApplyResult)
def apply_endpoint(payload: ApplyRequest, _: dict = Depends(require_super_admin)):
    results = service.apply(payload.target.model_dump(), payload.statements)
    applied = sum(1 for r in results if r["ok"])
    failed = len(results) - applied
    return ApplyResult(ok=failed == 0, applied=applied, failed=failed, results=results)
