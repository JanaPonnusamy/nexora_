from __future__ import annotations

"""Admin-only read endpoints for the append-only audit trail.

SECURITY & ACCESS:
- Read-only. Strictly no write, update, or delete endpoints exist.
- Restricted to administrators with platform/administration access.
- Reading the trail in bulk via the export endpoint is itself an auditable action
  and writes an `audit.export` row to the trail.
"""

import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from dependencies.auth import get_current_user, has_full_access
from .models import (
    AuditFilterOptionsResponse,
    AuditFilterParams,
    AuditListResponse,
)
from .repository import AuditRepository
from .writer import record_audit

router = APIRouter(prefix="/api/audit-logs", tags=["Audit Logs"])
_repo = AuditRepository()


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Ensure the requesting user has administrator access to the audit trail."""
    if not has_full_access(current_user):
        # Also check if role has ADMINISTRATION rights
        roles = current_user.get("role_names", [])
        if not any(r in {"SUPER_ADMIN", "PLATFORM_OWNER", "ADMIN", "ADMINISTRATOR"} for r in roles):
            raise HTTPException(
                status_code=403,
                detail="Access denied: Audit log inspection requires administrative privileges",
            )
    return current_user


@router.get("", response_model=AuditListResponse)
def list_audit_logs(
    request: Request,
    search: Optional[str] = Query(None, description="Substring search across actor, action, target, reason, IP"),
    action: Optional[str] = Query(None, description="Exact action name filter"),
    category: Optional[str] = Query(None, description="Category filter"),
    actor_id: Optional[str] = Query(None, description="Actor ID filter"),
    actor_role: Optional[str] = Query(None, description="Actor role filter"),
    target_type: Optional[str] = Query(None, description="Target entity type"),
    target_id: Optional[str] = Query(None, description="Target entity ID"),
    status: Optional[str] = Query(None, description="Status filter (success/failure)"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD or ISO)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD or ISO)"),
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(25, ge=1, le=100, description="Items per page (max 100)"),
    current_user: dict = Depends(_require_admin),
):
    """Paginated listing of audit logs, sorted by timestamp DESC."""
    params = AuditFilterParams(
        search=search,
        action=action,
        category=category,
        actor_id=actor_id,
        actor_role=actor_role,
        target_type=target_type,
        target_id=target_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    try:
        return _repo.search(params)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))


@router.get("/filters", response_model=AuditFilterOptionsResponse)
def get_filter_options(current_user: dict = Depends(_require_admin)):
    """Distinct filter options computed across the entire audit table."""
    return _repo.filter_options()


@router.get("/export")
def export_audit_logs(
    request: Request,
    search: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    actor_id: Optional[str] = Query(None),
    actor_role: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    target_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    current_user: dict = Depends(_require_admin),
):
    """Export filtered audit logs as a CSV file (capped at 10,000 records).
    
    CRITICAL: This endpoint writes its own `audit.export` audit row.
    """
    params = AuditFilterParams(
        search=search,
        action=action,
        category=category,
        actor_id=actor_id,
        actor_role=actor_role,
        target_type=target_type,
        target_id=target_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )

    try:
        rows = _repo.export(params, max_limit=10000)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))

    # Self-auditing: Record the bulk audit export action
    record_audit(
        ctx=request,
        action="audit.export",
        category="audit",
        target_type="audit_logs",
        target_label=f"Audit Export ({len(rows)} rows)",
        reason=f"Administrator exported {len(rows)} audit log rows to CSV",
        metadata={
            "exported_rows": len(rows),
            "filters": {k: v for k, v in params.model_dump().items() if v is not None},
        },
        actor_override={
            "actor_id": current_user.get("sub"),
            "actor_email": current_user.get("username"),
            "actor_name": current_user.get("username"),
        },
    )

    # Build CSV with UTF-8 BOM so Microsoft Excel opens it seamlessly
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM

    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Timestamp (UTC)",
        "Action",
        "Category",
        "Status",
        "Actor Name",
        "Actor Email",
        "Actor Role",
        "Target Type",
        "Target ID",
        "Target Label",
        "Reason",
        "IP Address",
        "Device / OS",
        "Error Message",
        "Metadata (JSON)",
    ])

    for r in rows:
        writer.writerow([
            r.get("timestamp") or "",
            r.get("action") or "",
            r.get("category") or "",
            r.get("status") or "",
            r.get("actor_name") or "",
            r.get("actor_email") or "",
            r.get("actor_role") or "",
            r.get("target_type") or "",
            r.get("target_id") or "",
            r.get("target_label") or "",
            r.get("reason") or "",
            r.get("ip") or "",
            r.get("device") or "",
            r.get("error_message") or "",
            r.get("metadata") or "",
        ])

    csv_data = output.getvalue().encode("utf-8")
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="audit-logs-export.csv"',
        },
    )
