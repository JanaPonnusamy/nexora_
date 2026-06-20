
# Architecture freeze:
#   Heartbeat = Agent Health (store_agent_registry / agent_heartbeat_log) -- never
#               touches the store database.
#   Sync = Business Data -- store DB is read-only and connected only during a sync
#          execution. Store status is derived from store_agent_registry +
#          agent_heartbeat_log + sync_execution only.
from fastapi import APIRouter, HTTPException
from services.sync_admin_service import SyncAdminService
from dtos.sync_request import SyncTableRequest, SyncTableStatusRequest, ColumnMappingRequest

router = APIRouter(prefix="/api/sync", tags=["Sync Administration"])

# ===== Control Center / Schedules / Store Health / History (read-only) =====

@router.get("/control-center")
def control_center():
    return SyncAdminService().control_center()

@router.get("/schedules")
def get_schedules():
    return SyncAdminService().get_schedules()

@router.get("/store-health")
def store_health():
    return SyncAdminService().store_health()

@router.get("/history")
def get_history():
    return SyncAdminService().get_history()

@router.get("/history/{sync_id}/details")
def get_history_details(sync_id: int):
    return SyncAdminService().get_history_details(sync_id)

# ===== Table Configuration =====

@router.get("/catalog/tables")
def catalog_tables(search: str | None = None):
    return SyncAdminService().catalog_tables(search)

@router.get("/tables")
def get_tables():
    return SyncAdminService().get_tables()

@router.get("/tables/{sync_table_id}")
def get_table(sync_table_id: str):
    table = SyncAdminService().get_table_by_id(sync_table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Sync table not found")
    return table

@router.post("/tables", status_code=201)
def create_table(body: SyncTableRequest):
    svc = SyncAdminService()
    table_name = body.table_name.strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="Table name is required")
    error, watermark, window = svc.normalize_mode_fields(body.sync_mode, body.watermark_column, body.window_days)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if svc.table_name_exists(table_name):
        raise HTTPException(status_code=400, detail="Table is already configured")
    new_id = svc.create_table(table_name, body.sync_mode.upper(), watermark, window,
                              body.custom_where, body.sync_order, body.is_active)
    return svc.get_table_by_id(str(new_id))

@router.put("/tables/{sync_table_id}")
def update_table(sync_table_id: str, body: SyncTableRequest):
    svc = SyncAdminService()
    table_name = body.table_name.strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="Table name is required")
    error, watermark, window = svc.normalize_mode_fields(body.sync_mode, body.watermark_column, body.window_days)
    if error:
        raise HTTPException(status_code=400, detail=error)
    if not svc.get_table_by_id(sync_table_id):
        raise HTTPException(status_code=404, detail="Sync table not found")
    if svc.table_name_exists(table_name, sync_table_id):
        raise HTTPException(status_code=400, detail="Table is already configured")
    svc.update_table(sync_table_id, table_name, body.sync_mode.upper(), watermark, window,
                     body.custom_where, body.sync_order)
    return svc.get_table_by_id(sync_table_id)

@router.patch("/tables/{sync_table_id}/status")
def set_table_status(sync_table_id: str, body: SyncTableStatusRequest):
    svc = SyncAdminService()
    if not svc.get_table_by_id(sync_table_id):
        raise HTTPException(status_code=404, detail="Sync table not found")
    svc.set_table_active(sync_table_id, body.is_active)
    return svc.get_table_by_id(sync_table_id)

# ===== Column Mapping =====

@router.get("/tables/{sync_table_id}/columns")
def get_table_columns(sync_table_id: str):
    result = SyncAdminService().get_table_columns(sync_table_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Sync table not found")
    return result

@router.put("/mappings")
def upsert_mapping(body: ColumnMappingRequest):
    SyncAdminService().upsert_mapping(body)
    return {"success": True, "message": "Column mapping saved"}
