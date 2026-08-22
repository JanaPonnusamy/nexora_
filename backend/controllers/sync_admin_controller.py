
from __future__ import annotations

# Architecture freeze:
#   Heartbeat = Agent Health (store_agent_registry / agent_heartbeat_log) -- never
#               touches the store database.
#   Sync = Business Data -- store DB is read-only and connected only during a sync
#          execution. Store status is derived from store_agent_registry +
#          agent_heartbeat_log + sync_execution only.
from fastapi import APIRouter, Depends, HTTPException, Request
from services.sync_admin_service import SyncAdminService
from dtos.sync_request import (
    SyncTableRequest, SyncTableStatusRequest, ColumnMappingRequest,
    ScheduleRequest, ScheduleSuspendRequest, ScheduleStatusRequest,
)
from dependencies.auth import get_current_user
from modules.audit.writer import record_audit
from modules.audit.diff import compute_mutation_diff
from modules.audit.context import AuditContext

router = APIRouter(prefix="/api/sync", tags=["Sync Administration"])

# ===== Control Center / Store Health / History (read-only) =====

@router.get("/control-center")
def control_center():
    return SyncAdminService().control_center()

# ===== Schedules (CRUD + suspend + seed) =====

@router.get("/schedules")
def get_schedules():
    return SyncAdminService().get_schedules()

@router.post("/schedules", status_code=201)
def create_schedule(body: ScheduleRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = SyncAdminService()
    error, schedule_type, start_dt = svc.validate_schedule(body)
    if error:
        raise HTTPException(status_code=400, detail=error)
    new_id = svc.create_schedule(body, schedule_type, start_dt)
    res = svc.get_schedule(new_id)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.schedule.create",
        category="sync",
        target_type="sync_schedule",
        target_id=str(new_id),
        target_label=body.schedule_name,
        reason=f"Created sync schedule '{body.schedule_name}' ({body.frequency_type})",
        metadata={"schedule_name": body.schedule_name, "frequency_type": body.frequency_type},
    )

    return res

@router.put("/schedules/{schedule_id}")
def update_schedule(schedule_id: int, body: ScheduleRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = SyncAdminService()
    existing = svc.get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    error, schedule_type, start_dt = svc.validate_schedule(body)
    if error:
        raise HTTPException(status_code=400, detail=error)
    svc.update_schedule(schedule_id, body, schedule_type, start_dt)
    res = svc.get_schedule(schedule_id)

    changed_fields, diff_details = compute_mutation_diff(
        existing if isinstance(existing, dict) else {},
        {"schedule_name": body.schedule_name, "frequency_type": body.frequency_type},
    )
    changed_str = ", ".join(changed_fields) if changed_fields else "no field changes"

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.schedule.update",
        target_type="sync_schedule",
        target_id=str(schedule_id),
        target_label=body.schedule_name,
        reason=f"Updated sync schedule '{body.schedule_name}' (changed: {changed_str})",
        metadata={"diff": diff_details, "changed_fields": changed_fields},
    )

    return res

@router.patch("/schedules/{schedule_id}/status")
def set_schedule_status(schedule_id: int, body: ScheduleStatusRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = SyncAdminService()
    existing = svc.get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    svc.set_schedule_status(schedule_id, body.is_enabled)
    res = svc.get_schedule(schedule_id)

    verb = "Enabled" if body.is_enabled else "Disabled"
    name = existing.get("schedule_name", str(schedule_id)) if isinstance(existing, dict) else str(schedule_id)
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.schedule.status.update",
        target_type="sync_schedule",
        target_id=str(schedule_id),
        target_label=name,
        reason=f"{verb} sync schedule '{name}'",
        metadata={"is_enabled": body.is_enabled},
    )

    return res

@router.patch("/schedules/{schedule_id}/suspend")
def suspend_schedule(schedule_id: int, body: ScheduleSuspendRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = SyncAdminService()
    existing = svc.get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    svc.suspend_schedule(schedule_id, body.suspended_until)
    res = svc.get_schedule(schedule_id)

    name = existing.get("schedule_name", str(schedule_id)) if isinstance(existing, dict) else str(schedule_id)
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.schedule.suspend",
        category="sync",
        target_type="sync_schedule",
        target_id=str(schedule_id),
        target_label=name,
        reason=f"Suspended sync schedule '{name}' until {body.suspended_until or 'indefinite'}",
        metadata={"suspended_until": body.suspended_until},
    )

    return res

@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    svc = SyncAdminService()
    existing = svc.get_schedule(schedule_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Schedule not found")
    svc.delete_schedule(schedule_id)

    name = existing.get("schedule_name", str(schedule_id)) if isinstance(existing, dict) else str(schedule_id)
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.schedule.delete",
        category="sync",
        target_type="sync_schedule",
        target_id=str(schedule_id),
        target_label=name,
        reason=f"Deleted sync schedule '{name}'",
        metadata={"deleted_schedule_id": schedule_id},
    )

    return None

@router.post("/schedules/seed")
def seed_schedules():
    return SyncAdminService().seed_default_schedules()

@router.get("/store-health")
def store_health():
    return SyncAdminService().store_health()

@router.get("/history")
def get_history(
    store_id: str | None = None,
    status: str | None = None,
    execution_type: str | None = None,
    sync_mode: str | None = None,
    search: str | None = None,
    limit: int = 200,
):
    return SyncAdminService().get_history(
        store_id=store_id, status=status, execution_type=execution_type,
        sync_mode=sync_mode, search=search, limit=limit)

@router.get("/history/statistics")
def history_statistics():
    return SyncAdminService().get_statistics()

@router.get("/history/{execution_id}")
def get_execution_summary(execution_id: str):
    summary = SyncAdminService().get_execution_summary(execution_id)
    if not summary:
        raise HTTPException(status_code=404, detail="Execution not found")
    return summary

@router.get("/history/{execution_id}/tables")
def get_execution_tables(execution_id: str):
    return SyncAdminService().get_execution_tables(execution_id)

@router.get("/history/{execution_id}/chunks")
def get_execution_chunks(execution_id: str, table_name: str | None = None):
    return SyncAdminService().get_execution_chunks(execution_id, table_name)

@router.get("/history/{execution_id}/errors")
def get_execution_errors(execution_id: str):
    return SyncAdminService().get_execution_errors(execution_id)

# ===== Table Configuration =====

@router.get("/catalog/tables")
def catalog_tables(search: str | None = None):
    return SyncAdminService().catalog_tables(search)

@router.get("/tables")
def get_tables():
    return SyncAdminService().get_tables()

@router.get("/tables/available")
def available_tables(search: str | None = None):
    return SyncAdminService().available_tables(search)

@router.get("/tables/{sync_table_id}")
def get_table(sync_table_id: str):
    table = SyncAdminService().get_table_by_id(sync_table_id)
    if not table:
        raise HTTPException(status_code=404, detail="Sync table not found")
    return table

@router.post("/tables", status_code=201)
def create_table(body: SyncTableRequest, request: Request, current_user: dict = Depends(get_current_user)):
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
    res = svc.get_table_by_id(str(new_id))

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.table.create",
        category="sync",
        target_type="sync_table",
        target_id=str(new_id),
        target_label=table_name,
        reason=f"Configured sync table '{table_name}' ({body.sync_mode.upper()})",
        metadata={"table_name": table_name, "sync_mode": body.sync_mode.upper()},
    )

    return res

@router.put("/tables/{sync_table_id}")
def update_table(sync_table_id: str, body: SyncTableRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = SyncAdminService()
    table_name = body.table_name.strip()
    if not table_name:
        raise HTTPException(status_code=400, detail="Table name is required")
    error, watermark, window = svc.normalize_mode_fields(body.sync_mode, body.watermark_column, body.window_days)
    if error:
        raise HTTPException(status_code=400, detail=error)
    existing = svc.get_table_by_id(sync_table_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Sync table not found")
    if svc.table_name_exists(table_name, sync_table_id):
        raise HTTPException(status_code=400, detail="Table is already configured")

    changed_fields, diff_details = compute_mutation_diff(
        existing if isinstance(existing, dict) else {},
        {"table_name": table_name, "sync_mode": body.sync_mode.upper()},
    )
    changed_str = ", ".join(changed_fields) if changed_fields else "no field changes"

    svc.update_table(sync_table_id, table_name, body.sync_mode.upper(), watermark, window,
                     body.custom_where, body.sync_order)
    res = svc.get_table_by_id(sync_table_id)

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.table.update",
        target_type="sync_table",
        target_id=sync_table_id,
        target_label=table_name,
        reason=f"Updated sync table '{table_name}' (changed: {changed_str})",
        metadata={"diff": diff_details, "changed_fields": changed_fields},
    )

    return res

@router.patch("/tables/{sync_table_id}/status")
def set_table_status(sync_table_id: str, body: SyncTableStatusRequest, request: Request, current_user: dict = Depends(get_current_user)):
    svc = SyncAdminService()
    existing = svc.get_table_by_id(sync_table_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Sync table not found")
    svc.set_table_active(sync_table_id, body.is_active)
    res = svc.get_table_by_id(sync_table_id)

    verb = "Activated" if body.is_active else "Deactivated"
    table_name = existing.get("table_name", sync_table_id) if isinstance(existing, dict) else sync_table_id
    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.table.status.update",
        target_type="sync_table",
        target_id=sync_table_id,
        target_label=str(table_name),
        reason=f"{verb} sync table '{table_name}'",
        metadata={"is_active": body.is_active},
    )

    return res

# ===== Column Mapping =====

@router.get("/tables/{sync_table_id}/columns")
def get_table_columns(sync_table_id: str):
    result = SyncAdminService().get_table_columns(sync_table_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Sync table not found")
    return result

@router.put("/mappings")
def upsert_mapping(body: ColumnMappingRequest, request: Request, current_user: dict = Depends(get_current_user)):
    SyncAdminService().upsert_mapping(body)

    flags = [f for f, on in (
        ("selected", body.is_selected), ("pk", body.is_pk),
        ("hash", body.is_hash), ("watermark", body.is_watermark),
    ) if on]
    flag_str = ", ".join(flags) if flags else "no flags"

    record_audit(
        ctx=AuditContext.from_request(request, user=current_user),
        action="sync.mapping.update",
        category="sync",
        target_type="sync_table",
        target_id=str(body.sync_table_id),
        target_label=f"{body.table_name}.{body.column_name}",
        reason=f"Updated column mapping '{body.table_name}.{body.column_name}' ({flag_str})",
        metadata={
            "sync_table_id": body.sync_table_id,
            "table_name": body.table_name,
            "column_name": body.column_name,
            "is_selected": body.is_selected,
            "is_pk": body.is_pk,
            "is_hash": body.is_hash,
            "is_watermark": body.is_watermark,
            "column_order": body.column_order,
        },
    )

    return {"success": True, "message": "Column mapping saved"}
