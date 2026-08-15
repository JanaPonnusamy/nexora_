from __future__ import annotations

"""Action taxonomy, category derivation, and endpoint registry.

THREE VALID STATES:
1. In AUDITED_ENDPOINTS and instrumented in handler:
   Emits both success rows (composed by handler) and failure rows (via failure middleware).
2. In AUDITED_ENDPOINTS, NOT instrumented in handler:
   Failure-only pattern. Used for sensitive gates where success is implicit in the downstream
   action, but unauthorized attempts or failures must be captured.
3. In UNAUDITED_ENDPOINTS:
   Deliberately excluded high-volume, low-signal traffic (health checks, polling loops,
   public read-only metadata lookups).
"""

from typing import Any, Dict, Optional
from .models import AuditCategory

# Explicit category overrides for actions whose first segment does not match their category.
# NOTE: If this map grows significantly, action names are drifting from taxonomy conventions
# and should be normalized instead of adding entries here.
_ACTION_CATEGORY_OVERRIDES: Dict[str, str] = {
    "login": AuditCategory.AUTH.value,
    "logout": AuditCategory.AUTH.value,
    "setup_login": AuditCategory.AUTH.value,
    "export": AuditCategory.AUDIT.value,
    "security.credential_mint": AuditCategory.AUTH.value,
}


def category_for_action(action: str) -> str:
    """Derive the category from an action name.
    
    NEVER THROWS: Falls back to 'system' or default category if unrecognized.
    A miscategorized row is a minor nuisance, but raising an exception would abort
    the audited business transaction, defeating the core design principle that
    logging must never take down operations.
    """
    if not action:
        return AuditCategory.SYSTEM.value

    act = action.strip()
    if act in _ACTION_CATEGORY_OVERRIDES:
        return _ACTION_CATEGORY_OVERRIDES[act]

    # Extract first dot-separated segment
    segment = act.split(".")[0].lower()
    valid_categories = {c.value for c in AuditCategory}
    if segment in valid_categories:
        return segment

    return AuditCategory.SYSTEM.value


# =============================================================================
# AUDITED ENDPOINTS REGISTRY
# Maps HTTP method + route path template to default action and category
# =============================================================================
AUDITED_ENDPOINTS: Dict[str, Dict[str, str]] = {
    # ----- Authentication -----
    "POST /api/auth/login": {
        "action": "auth.login",
        "category": AuditCategory.AUTH.value,
    },
    "POST /api/auth/setup-login": {
        "action": "auth.setup_login",
        "category": AuditCategory.AUTH.value,
    },
    "GET /api/auth/me": {
        "action": "auth.session.validate",
        "category": AuditCategory.AUTH.value,
    },

    # ----- User Management -----
    "POST /api/users": {
        "action": "user.create",
        "category": AuditCategory.USER.value,
    },
    "PUT /api/users/{user_id}": {
        "action": "user.update",
        "category": AuditCategory.USER.value,
    },
    "PATCH /api/users/{user_id}/status": {
        "action": "user.status.update",
        "category": AuditCategory.USER.value,
    },
    "POST /api/user-roles": {
        "action": "user.role.assign",
        "category": AuditCategory.USER.value,
    },
    "DELETE /api/user-roles": {
        "action": "user.role.remove",
        "category": AuditCategory.USER.value,
    },

    # ----- Role & Permissions -----
    "POST /api/roles": {
        "action": "role.create",
        "category": AuditCategory.ROLE.value,
    },
    "PUT /api/roles/{role_id}": {
        "action": "role.update",
        "category": AuditCategory.ROLE.value,
    },
    "DELETE /api/roles/{role_id}": {
        "action": "role.delete",
        "category": AuditCategory.ROLE.value,
    },
    "POST /api/role-module-access": {
        "action": "role.permission.update",
        "category": AuditCategory.ROLE.value,
    },
    "PUT /api/permissions/matrix": {
        "action": "role.permissions.matrix_update",
        "category": AuditCategory.ROLE.value,
    },

    # ----- Tenants & Stores -----
    "POST /api/tenants": {
        "action": "tenant.create",
        "category": AuditCategory.TENANT.value,
    },
    "PUT /api/tenants/{tenant_id}": {
        "action": "tenant.update",
        "category": AuditCategory.TENANT.value,
    },
    "PATCH /api/tenants/{tenant_id}/status": {
        "action": "tenant.status.update",
        "category": AuditCategory.TENANT.value,
    },
    "POST /api/stores": {
        "action": "store.create",
        "category": AuditCategory.STORE.value,
    },
    "PUT /api/stores/{store_id}": {
        "action": "store.update",
        "category": AuditCategory.STORE.value,
    },
    "PATCH /api/stores/{store_id}/status": {
        "action": "store.status.update",
        "category": AuditCategory.STORE.value,
    },
    "PUT /api/stores/{store_id}/agent-config": {
        "action": "store.agent_config.update",
        "category": AuditCategory.STORE.value,
    },

    # ----- Modules -----
    "PATCH /api/modules/{module_id}/status": {
        "action": "module.status.update",
        "category": AuditCategory.MODULE.value,
    },

    # ----- Sync Administration -----
    "POST /api/sync/tables": {
        "action": "sync.table.create",
        "category": AuditCategory.SYNC.value,
    },
    "PUT /api/sync/tables/{sync_table_id}": {
        "action": "sync.table.update",
        "category": AuditCategory.SYNC.value,
    },
    "PATCH /api/sync/tables/{sync_table_id}/status": {
        "action": "sync.table.status.update",
        "category": AuditCategory.SYNC.value,
    },
    "PUT /api/sync/mappings": {
        "action": "sync.mapping.update",
        "category": AuditCategory.SYNC.value,
    },
    "POST /api/sync/schedules": {
        "action": "sync.schedule.create",
        "category": AuditCategory.SYNC.value,
    },
    "PUT /api/sync/schedules/{schedule_id}": {
        "action": "sync.schedule.update",
        "category": AuditCategory.SYNC.value,
    },
    "PATCH /api/sync/schedules/{schedule_id}/status": {
        "action": "sync.schedule.status.update",
        "category": AuditCategory.SYNC.value,
    },
    "PATCH /api/sync/schedules/{schedule_id}/suspend": {
        "action": "sync.schedule.suspend",
        "category": AuditCategory.SYNC.value,
    },
    "POST /api/sync/control": {
        "action": "sync.control.action",
        "category": AuditCategory.SYNC.value,
    },

    # ----- Audit Trail Self-Auditing -----
    "GET /api/audit-logs/export": {
        "action": "audit.export",
        "category": AuditCategory.AUDIT.value,
    },
}


# =============================================================================
# UNAUDITED ENDPOINTS (Explicit Exclusions)
# =============================================================================
UNAUDITED_ENDPOINTS: Dict[str, str] = {
    # High-frequency poll loop: store agents check for tasks every few seconds
    "GET /api/sync/tasks/pending/{store_id}": "High-frequency task polling loop; logging would flood DB without forensic value.",
    # High-frequency chunk transfers: data transport covered at execution summary level
    "POST /api/sync/chunks/upload": "High-throughput binary payload transfer; chunk metrics are tracked in sync execution summary.",
    "POST /api/sync/chunks/ack": "High-throughput protocol acknowledgment.",
    # Read-only UI status queries
    "GET /api/sync/control-center": "Read-only live dashboard state polling.",
    "GET /api/sync/live": "Read-only live store sync monitoring stream.",
    "GET /api/audit-logs": "Interactive UI search and pagination queries.",
    "GET /api/audit-logs/filters": "Filter dropdown options population query.",
}


def lookup_endpoint_action(method: str, path: str) -> Optional[Dict[str, str]]:
    """Match an incoming HTTP request method and path against AUDITED_ENDPOINTS."""
    key = f"{method.upper()} {path}"
    if key in AUDITED_ENDPOINTS:
        return AUDITED_ENDPOINTS[key]

    # Pattern-based matching for parameterized paths (e.g. /api/users/123)
    for endpoint_pattern, spec in AUDITED_ENDPOINTS.items():
        ep_method, ep_path = endpoint_pattern.split(" ", 1)
        if method.upper() != ep_method:
            continue
        # Convert {param} to regex pattern
        import re
        regex_pattern = "^" + re.sub(r"\{[^/]+\}", r"[^/]+", ep_path) + "$"
        if re.match(regex_pattern, path):
            return spec

    return None
