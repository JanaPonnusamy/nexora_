from __future__ import annotations

"""Data access and immutability guards for the append-only audit trail.

IMMUTABILITY NOTICE:
The guards in this repository guard against mistakes and bugs in application
code. They are NOT a security boundary: raw driver calls or direct DB shell
sessions can walk straight past application-level guards. The true security
boundary is a dedicated database user granted only INSERT and SELECT on
dbo.audit_logs — this should be enforced as an infrastructure/ops task.

RETENTION POLICY:
Do not add a TTL / auto-expiry index to this table. A TTL is a silent delete:
a mistyped expiry duration would destroy the compliance audit trail irreversibly.
If bounded retention is ever required, it should be implemented as an explicit,
audited periodic cold-storage archival job, not an automatic database TTL.

INDEXING STRATEGY & FREE-TEXT SEARCH:
Every index ends in `timestamp DESC` to ensure sorting is index-served rather than
falling back to costly in-memory sorts.
No full-text index is created: free-text search is intentionally implemented via
substring matching so partial search terms (e.g. searching 'north' matches 'northwind.in')
work reliably. Because the query orders by `timestamp DESC`, the query engine walks
the index in order and short-circuits once the page is full.
"""

import json
import re
from datetime import datetime, time, timezone
from uuid import uuid4
from typing import Any, Optional, Tuple, List, Dict

from config.database import get_connection
from .models import (
    ActorRole,
    AuditCategory,
    AuditEntry,
    AuditFilterOptionsResponse,
    AuditFilterParams,
    AuditImmutableError,
    AuditListResponse,
    AuditStatus,
    AuditActorOption,
)


def ensure_schema() -> None:
    """Create dbo.audit_logs and its timestamp-descending composite indexes."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            IF OBJECT_ID('dbo.audit_logs', 'U') IS NULL
            BEGIN
                CREATE TABLE dbo.audit_logs (
                    log_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT PK_audit_logs PRIMARY KEY,
                    actor_id NVARCHAR(64) NULL,
                    actor_role NVARCHAR(20) NOT NULL,
                    actor_email NVARCHAR(255) NULL,
                    actor_name NVARCHAR(255) NULL,
                    action NVARCHAR(64) NOT NULL,
                    category NVARCHAR(30) NOT NULL,
                    target_type NVARCHAR(64) NULL,
                    target_id NVARCHAR(255) NULL,
                    target_label NVARCHAR(255) NULL,
                    reason NVARCHAR(500) NULL,
                    metadata NVARCHAR(MAX) NULL,
                    ip NVARCHAR(45) NULL,
                    user_agent NVARCHAR(512) NULL,
                    device NVARCHAR(100) NULL,
                    country NVARCHAR(2) NULL,
                    status NVARCHAR(20) NOT NULL,
                    error_message NVARCHAR(500) NULL,
                    timestamp DATETIME2(3) NOT NULL
                );
            END;

            -- Default listing and export index
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.audit_logs') AND name = 'IX_audit_logs_timestamp')
            BEGIN
                CREATE INDEX IX_audit_logs_timestamp ON dbo.audit_logs(timestamp DESC);
            END;

            -- Action filter index
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.audit_logs') AND name = 'IX_audit_logs_action_timestamp')
            BEGIN
                CREATE INDEX IX_audit_logs_action_timestamp ON dbo.audit_logs(action, timestamp DESC);
            END;

            -- Category filter index
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.audit_logs') AND name = 'IX_audit_logs_category_timestamp')
            BEGIN
                CREATE INDEX IX_audit_logs_category_timestamp ON dbo.audit_logs(category, timestamp DESC);
            END;

            -- Actor investigation query index
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.audit_logs') AND name = 'IX_audit_logs_actor_timestamp')
            BEGIN
                CREATE INDEX IX_audit_logs_actor_timestamp ON dbo.audit_logs(actor_id, timestamp DESC);
            END;

            -- Target lookup index (prefix also serves target_type only)
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.audit_logs') AND name = 'IX_audit_logs_target_timestamp')
            BEGIN
                CREATE INDEX IX_audit_logs_target_timestamp ON dbo.audit_logs(target_type, target_id, timestamp DESC);
            END;

            -- Failure feed index
            IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.audit_logs') AND name = 'IX_audit_logs_status_timestamp')
            BEGIN
                CREATE INDEX IX_audit_logs_status_timestamp ON dbo.audit_logs(status, timestamp DESC);
            END;
            """
        )
        conn.commit()
    finally:
        conn.close()


def _parse_date_bound(date_str: str, is_end: bool = False) -> datetime:
    """Parse a date string and widen bare YYYY-MM-DD to the full UTC day."""
    s = date_str.strip()
    # If standard YYYY-MM-DD date
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        parsed = datetime.strptime(s, "%Y-%m-%d")
        if is_end:
            return datetime.combine(parsed.date(), time(23, 59, 59, 999000))
        return datetime.combine(parsed.date(), time(0, 0, 0, 0))
    # Otherwise try ISO format
    try:
        # Handle trailing Z
        normalized = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is not None:
            # Convert to UTC naive datetime for SQL Server DATETIME2
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception as e:
        raise ValueError(f"Invalid date format: '{date_str}'. Expected YYYY-MM-DD or ISO 8601 string.") from e


def build_filter_query(params: AuditFilterParams) -> Tuple[str, List[Any]]:
    """Shared filter builder for paginated listing and CSV export.
    
    Ensures that substring search, enum dropping, and date range bounds
    are identical across all read endpoints.
    """
    conditions: List[str] = []
    sql_params: List[Any] = []

    # 1. Free-text substring search across who/what/to-what/why/where
    if params.search:
        search_term = params.search.strip()
        if search_term:
            like_pattern = f"%{search_term}%"
            conditions.append(
                """(
                    actor_name LIKE ?
                    OR actor_email LIKE ?
                    OR action LIKE ?
                    OR target_label LIKE ?
                    OR target_id LIKE ?
                    OR reason LIKE ?
                    OR ip LIKE ?
                )"""
            )
            sql_params.extend([like_pattern] * 7)

    # 2. Action filter
    if params.action:
        act = params.action.strip()
        if act:
            conditions.append("action = ?")
            sql_params.append(act)

    # 3. Category filter (drop if not a valid category string)
    if params.category:
        cat = params.category.strip().lower()
        valid_cats = {c.value for c in AuditCategory}
        if cat in valid_cats:
            conditions.append("category = ?")
            sql_params.append(cat)

    # 4. Actor ID filter
    if params.actor_id:
        aid = params.actor_id.strip()
        if aid:
            conditions.append("actor_id = ?")
            sql_params.append(aid)

    # 5. Actor Role filter (drop invalid enum values)
    if params.actor_role:
        role = params.actor_role.strip().lower()
        if role in {r.value for r in ActorRole}:
            conditions.append("actor_role = ?")
            sql_params.append(role)

    # 6. Target Type filter
    if params.target_type:
        ttype = params.target_type.strip()
        if ttype:
            conditions.append("target_type = ?")
            sql_params.append(ttype)

    # 7. Target ID filter
    if params.target_id:
        tid = params.target_id.strip()
        if tid:
            conditions.append("target_id = ?")
            sql_params.append(tid)

    # 8. Status filter (drop invalid enum values)
    if params.status:
        st = params.status.strip().lower()
        if st in {s.value for s in AuditStatus}:
            conditions.append("status = ?")
            sql_params.append(st)

    # 9. Date range bounds with widening
    from_dt: Optional[datetime] = None
    to_dt: Optional[datetime] = None

    if params.from_date:
        from_dt = _parse_date_bound(params.from_date, is_end=False)
    if params.to_date:
        to_dt = _parse_date_bound(params.to_date, is_end=True)

    if from_dt and to_dt and from_dt > to_dt:
        raise ValueError(f"from_date ({params.from_date}) cannot be after to_date ({params.to_date})")

    if from_dt:
        conditions.append("timestamp >= ?")
        sql_params.append(from_dt)
    if to_dt:
        conditions.append("timestamp <= ?")
        sql_params.append(to_dt)

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where_clause, sql_params


class AuditRepository:
    """Repository managing append-only persistence and querying for dbo.audit_logs."""

    def insert(self, entry: AuditEntry) -> str:
        """Insert an audit log entry. Only append operations are allowed."""
        log_id = entry.log_id or str(uuid4())
        ts = entry.timestamp or datetime.utcnow()
        role_str = entry.actor_role.value if isinstance(entry.actor_role, ActorRole) else str(entry.actor_role)
        status_str = entry.status.value if isinstance(entry.status, AuditStatus) else str(entry.status)

        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO dbo.audit_logs (
                    log_id, actor_id, actor_role, actor_email, actor_name,
                    action, category, target_type, target_id, target_label,
                    reason, metadata, ip, user_agent, device, country,
                    status, error_message, timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                log_id,
                entry.actor_id,
                role_str,
                entry.actor_email,
                entry.actor_name,
                entry.action,
                entry.category,
                entry.target_type,
                entry.target_id,
                entry.target_label,
                entry.reason,
                entry.metadata,
                entry.ip,
                entry.user_agent,
                entry.device,
                entry.country,
                status_str,
                entry.error_message,
                ts,
            )
            conn.commit()
            return log_id
        finally:
            conn.close()

    # =========================================================================
    # IMMUTABILITY GUARDS: Rejects any attempt to mutate or delete audit log rows
    # =========================================================================

    def update(self, *args, **kwargs) -> None:
        raise AuditImmutableError("audit_logs is an append-only table: updates are strictly forbidden.")

    def delete(self, *args, **kwargs) -> None:
        raise AuditImmutableError("audit_logs is an append-only table: deletions are strictly forbidden.")

    def upsert(self, *args, **kwargs) -> None:
        raise AuditImmutableError("audit_logs is an append-only table: upserts are strictly forbidden.")

    def replace(self, *args, **kwargs) -> None:
        raise AuditImmutableError("audit_logs is an append-only table: replacements are strictly forbidden.")

    def save(self, *args, **kwargs) -> None:
        raise AuditImmutableError("audit_logs is an append-only table: re-saving modified rows is strictly forbidden.")

    # =========================================================================
    # QUERY METHODS
    # =========================================================================

    def search(self, params: AuditFilterParams) -> AuditListResponse:
        """Search and paginate audit logs, sorted by timestamp DESC."""
        where_clause, sql_params = build_filter_query(params)
        page_size = max(1, min(100, params.page_size))
        page = max(1, params.page)
        offset = (page - 1) * page_size

        conn = get_connection()
        try:
            cur = conn.cursor()

            # 1. Total count
            cur.execute(f"SELECT COUNT(*) FROM dbo.audit_logs {where_clause}", sql_params)
            total = cur.fetchone()[0]

            # 2. Paginated rows
            # T-SQL OFFSET-FETCH requires ORDER BY
            query = f"""
                SELECT
                    log_id, actor_id, actor_role, actor_email, actor_name,
                    action, category, target_type, target_id, target_label,
                    reason, metadata, ip, user_agent, device, country,
                    status, error_message, timestamp
                FROM dbo.audit_logs
                {where_clause}
                ORDER BY timestamp DESC
                OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """
            cur.execute(query, sql_params + [offset, page_size])
            rows = cur.fetchall()

            items = [self._row_to_dict(r) for r in rows]
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            return AuditListResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )
        finally:
            conn.close()

    def export(self, params: AuditFilterParams, max_limit: int = 10000) -> List[Dict[str, Any]]:
        """Fetch audit logs for CSV export, capped at max_limit."""
        where_clause, sql_params = build_filter_query(params)
        limit = max(1, min(10000, max_limit))

        conn = get_connection()
        try:
            cur = conn.cursor()
            query = f"""
                SELECT TOP ({limit})
                    log_id, actor_id, actor_role, actor_email, actor_name,
                    action, category, target_type, target_id, target_label,
                    reason, metadata, ip, user_agent, device, country,
                    status, error_message, timestamp
                FROM dbo.audit_logs
                {where_clause}
                ORDER BY timestamp DESC
            """
            cur.execute(query, sql_params)
            rows = cur.fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def filter_options(self) -> AuditFilterOptionsResponse:
        """Fetch distinct filter options computed across the entire table.
        
        Takes each actor's most recent name/email snapshot by ordering by timestamp DESC.
        Categories come from the closed enum so all options are always available in the UI.
        """
        conn = get_connection()
        try:
            cur = conn.cursor()

            # Distinct actors with their most recent name and email snapshot
            cur.execute(
                """
                WITH RankedActors AS (
                    SELECT
                        actor_id,
                        actor_name,
                        actor_email,
                        actor_role,
                        ROW_NUMBER() OVER (PARTITION BY actor_id ORDER BY timestamp DESC) AS rn
                    FROM dbo.audit_logs
                    WHERE actor_id IS NOT NULL
                )
                SELECT actor_id, actor_name, actor_email, actor_role
                FROM RankedActors
                WHERE rn = 1
                ORDER BY actor_name, actor_id
                """
            )
            actor_rows = cur.fetchall()
            actors = [
                AuditActorOption(
                    actor_id=str(r[0]),
                    actor_name=r[1],
                    actor_email=r[2],
                    actor_role=r[3],
                )
                for r in actor_rows
            ]

            # Distinct actions
            cur.execute("SELECT DISTINCT action FROM dbo.audit_logs ORDER BY action")
            actions = [str(r[0]) for r in cur.fetchall() if r[0]]

            # Distinct target types
            cur.execute("SELECT DISTINCT target_type FROM dbo.audit_logs WHERE target_type IS NOT NULL ORDER BY target_type")
            target_types = [str(r[0]) for r in cur.fetchall() if r[0]]

            # Categories come from the closed enum
            categories = [c.value for c in AuditCategory]
            statuses = [s.value for s in AuditStatus]
            actor_roles = [r.value for r in ActorRole]

            return AuditFilterOptionsResponse(
                actors=actors,
                actions=actions,
                categories=categories,
                target_types=target_types,
                statuses=statuses,
                actor_roles=actor_roles,
            )
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row: Any) -> Dict[str, Any]:
        """Format a database row into a serialized dictionary."""
        # Convert datetime to ISO string
        ts = row[18]
        if isinstance(ts, datetime):
            ts_str = ts.isoformat() + "Z" if ts.tzinfo is None else ts.isoformat()
        else:
            ts_str = str(ts) if ts else None

        return {
            "log_id": str(row[0]),
            "actor_id": str(row[1]) if row[1] is not None else None,
            "actor_role": row[2],
            "actor_email": row[3],
            "actor_name": row[4],
            "action": row[5],
            "category": row[6],
            "target_type": row[7],
            "target_id": str(row[8]) if row[8] is not None else None,
            "target_label": row[9],
            "reason": row[10],
            "metadata": row[11],  # JSON string or None
            "ip": row[12],
            "user_agent": row[13],
            "device": row[14],
            "country": row[15],
            "status": row[16],
            "error_message": row[17],
            "timestamp": ts_str,
        }
