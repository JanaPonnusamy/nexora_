from __future__ import annotations

"""Failure capture middleware for audited endpoints.

RATIONALE:
Handlers compose and record their own SUCCESS rows because only the handler
understands the business entity context, target labels, and before/after mutation diffs.
In contrast, failure attempts all share a common structure: early returns, validation
errors, unhandled exceptions, and critically: AUTHORIZATION / AUTHENTICATION DENIALS.

An authentication or authorization failure (e.g. 401 Unauthorized or 403 Forbidden
from require_auth or admin permission guards) aborts the request before it ever reaches
the handler body. No handler could ever record an authorization denial. Capturing unauthorized
attempts ("someone without permission attempted to delete a role or suspend a store")
is one of the most critical compliance capabilities of this audit trail.

GAPS & RETURNING HANDLERS:
Handlers that report business failures by returning an error response model or None
rather than raising an HTTPException or error code are invisible to this middleware.
Those handlers must record their own explicit failure audit rows:
- `auth_controller.login` (when AuthService().login returns None)
- `auth_controller.setup_login` (when checksum or credentials fail)
"""

import json
import logging
from typing import Any, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config.security import decode_access_token
from .models import ActorRole, AuditStatus
from .context import AuditContext
from .taxonomy import lookup_endpoint_action
from .writer import record_audit

logger = logging.getLogger("nexora.audit.middleware")


class AuditFailureMiddleware(BaseHTTPMiddleware):
    """Intercepts request errors and authorization denials on audited endpoints."""

    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method
        path = request.url.path

        # Fast check: only process API endpoints
        if not path.startswith("/api/"):
            return await call_next(request)

        spec = lookup_endpoint_action(method, path)

        try:
            response = await call_next(request)

            # Check if response indicates an HTTP error (4xx or 5xx) on an audited endpoint
            if spec and response.status_code >= 400:
                self._record_failure_response(request, response.status_code, spec)

            return response

        except Exception as exc:
            # Unhandled server exceptions on an audited endpoint
            if spec:
                self._record_exception_failure(request, exc, spec)
            raise exc

    def _extract_actor_from_request(self, request: Request) -> AuditContext:
        """Attempt to extract actor information from bearer token if present."""
        auth_header = request.headers.get("authorization", "")
        user_claims = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            try:
                user_claims = decode_access_token(token)
            except Exception:
                pass

        return AuditContext.from_request(request, user=user_claims)

    def _record_failure_response(self, request: Request, status_code: int, spec: dict[str, str]) -> None:
        """Record an audit row for an HTTP 4xx/5xx failure or permission denial."""
        action = spec["action"]
        category = spec["category"]
        ctx = self._extract_actor_from_request(request)

        if status_code == 401:
            error_desc = "Authentication failed or token missing/expired"
            reason = f"Unauthorized attempt on {request.method} {request.url.path} (HTTP 401)"
        elif status_code == 403:
            error_desc = "Permission denied / insufficient role privileges"
            reason = f"Forbidden access attempt on {request.method} {request.url.path} (HTTP 403)"
        elif status_code == 404:
            error_desc = "Resource not found"
            reason = f"Target resource not found on {request.method} {request.url.path} (HTTP 404)"
        elif status_code == 422:
            error_desc = "Unprocessable entity / request schema validation failed"
            reason = f"Validation failed on {request.method} {request.url.path} (HTTP 422)"
        else:
            error_desc = f"HTTP {status_code} error"
            reason = f"Request failed with HTTP {status_code} on {request.method} {request.url.path}"

        metadata = {
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "status_code": status_code,
        }

        record_audit(
            ctx=ctx,
            action=action,
            category=category,
            status=AuditStatus.FAILURE,
            error_message=error_desc,
            reason=reason,
            metadata=metadata,
        )

    def _record_exception_failure(self, request: Request, exc: Exception, spec: dict[str, str]) -> None:
        """Record an audit row for an unhandled exception."""
        action = spec["action"]
        category = spec["category"]
        ctx = self._extract_actor_from_request(request)

        error_message = str(exc) or type(exc).__name__
        reason = f"Unhandled exception during {request.method} {request.url.path}: {type(exc).__name__}"

        metadata = {
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "exception_type": type(exc).__name__,
        }

        record_audit(
            ctx=ctx,
            action=action,
            category=category,
            status=AuditStatus.FAILURE,
            error_message=error_message[:500],
            reason=reason[:500],
            metadata=metadata,
        )
