from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from modules.sync import runtime_service

router = APIRouter(prefix="/api/sync", tags=["Sync Runtime"])
agent_router = APIRouter(prefix="/agent", tags=["Sync Agent"])


class TaskCreateRequest(BaseModel):
    tenant_id: str
    store_id: str
    execution_type: str = "FULL"
    sync_mode: str = "FULL"
    total_tables: int = 0


class FailRequest(BaseModel):
    message: Optional[str] = None


class ChunkUploadRequest(BaseModel):
    execution_id: str
    table_name: str
    chunk_no: int
    rows: List[Dict[str, Any]] = []
    total_rows: Optional[int] = None
    sync_type: Optional[str] = None


class ControlRequest(BaseModel):
    store_ids: List[str] = []
    action: str  # PAUSE | STOP


class TableMetricsRequest(BaseModel):
    execution_id: str
    table_name: str
    sync_type: Optional[str] = None
    rows_examined: int = 0
    rows_changed: int = 0
    rows_uploaded: int = 0
    rows_skipped: int = 0
    source_total: int = 0
    status: Optional[str] = None
    error_message: Optional[str] = None


class ChunkAckRequest(BaseModel):
    chunk_execution_id: int


class HeartbeatRequest(BaseModel):
    store_id: str
    tenant_id: Optional[str] = None
    agent_version: Optional[str] = None
    connection_type: Optional[str] = None
    ip_address: Optional[str] = None
    install_path: Optional[str] = None
    hostname: Optional[str] = None


@router.post("/tasks/create")
def create_task(payload: TaskCreateRequest):
    return runtime_service.create_task(payload.dict())


@router.get("/tasks/pending/{store_id}")
def pending_tasks(store_id: str):
    return runtime_service.get_pending_tasks(store_id)


@router.post("/tasks/{task_id}/start")
def start_task(task_id: str):
    return runtime_service.start_task(task_id)


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: str):
    return runtime_service.complete_task(task_id)


@router.post("/tasks/{task_id}/fail")
def fail_task(task_id: str, payload: FailRequest):
    return runtime_service.fail_task(task_id, payload.message)


@router.get("/configuration/{task_id}")
def configuration(task_id: str):
    result = runtime_service.get_configuration(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result


@router.post("/chunks/upload")
def upload_chunk(payload: ChunkUploadRequest):
    return runtime_service.upload_chunk(payload.dict())


@router.post("/chunks/ack")
def ack_chunk(payload: ChunkAckRequest):
    return runtime_service.ack_chunk(payload.chunk_execution_id)


@router.get("/chunks/status/{execution_id}")
def chunk_status(execution_id: str):
    return runtime_service.get_chunk_status(execution_id)


@router.get("/live")
def live_status():
    return runtime_service.get_live_status()


@router.post("/control")
def control(payload: ControlRequest):
    return runtime_service.control_stores(payload.store_ids, payload.action)


@router.post("/tables/report")
def report_table(payload: TableMetricsRequest):
    return runtime_service.report_table_metrics(payload.dict())


@router.get("/table-stats")
def table_stats():
    return runtime_service.get_table_statistics()


@agent_router.get("/tasks/poll")
def poll_tasks(store_id: str):
    return runtime_service.get_pending_tasks(store_id)


@agent_router.post("/register")
def register_agent(payload: HeartbeatRequest):
    return runtime_service.agent_heartbeat(payload.dict(), register=True)


@agent_router.post("/heartbeat")
def heartbeat(payload: HeartbeatRequest):
    return runtime_service.agent_heartbeat(payload.dict())


@router.post("/agents/sweep-offline")
def sweep_offline(threshold_seconds: int = 300):
    return runtime_service.mark_stale_agents_offline(threshold_seconds)
