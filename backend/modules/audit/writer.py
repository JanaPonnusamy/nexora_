from __future__ import annotations

"""Audit trail writer exposing non-throwing and strict entry points.

THE TWO ENTRY POINTS:
1. record_audit(ctx, ...):
   NEVER THROWS. Catches and logs internal errors. Used fire-and-forget
   for operations that have already completed or side-effects that have landed.
   Failing a user response because an audit write failed would cause non-idempotent
   retries on actions that already succeeded.

2. record_audit_strict(ctx, ...):
   THROWS ON FAILURE. Used ONLY where recording the audit trail is an absolute
   prerequisite before issuing credentials (SSO minting, API keys, password reveals).
   Must be awaited before the credential is handed to the client.
"""

import logging
from typing import Any, Optional, Union
from fastapi import Request

from .models import ActorRole, AuditEntry, AuditStatus
from .context import AuditContext
from .redaction import redact_and_bound_metadata
from .taxonomy import category_for_action
from .repository import AuditRepository

logger = logging.getLogger("nexora.audit")
_repo = AuditRepository()


def _normalize_context(ctx: Optional[Union[AuditContext, Request, dict[str, Any]]]) -> AuditContext:
    """Normalize various context input types into a standard AuditContext."""
    if ctx is None:
        return AuditContext()
    if isinstance(ctx, AuditContext):
        return ctx
    if isinstance(ctx, Request):
        return AuditContext.from_request(ctx)
    if isinstance(ctx, dict):
        # Could be user claims dictionary or context dict
        return AuditContext(
            actor_id=ctx.get("actor_id") or ctx.get("sub") or ctx.get("user_id"),
            actor_role=ctx.get("actor_role") or (ActorRole.ADMIN if ctx.get("is_platform_user") else ActorRole.SYSTEM),
            actor_email=ctx.get("actor_email") or ctx.get("email") or ctx.get("username"),
            actor_name=ctx.get("actor_name") or ctx.get("full_name") or ctx.get("first_name"),
            ip=ctx.get("ip"),
            user_agent=ctx.get("user_agent"),
            device=ctx.get("device"),
            country=ctx.get("country"),
        )
    return AuditContext()


def _compose_entry(
    ctx: Optional[Union[AuditContext, Request, dict[str, Any]]],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[Any] = None,
    target_label: Optional[str] = None,
    reason: Optional[str] = None,
    metadata: Optional[Any] = None,
    status: AuditStatus = AuditStatus.SUCCESS,
    error_message: Optional[str] = None,
    category: Optional[str] = None,
    actor_override: Optional[dict[str, Any]] = None,
) -> AuditEntry:
    """Compose and sanitize an AuditEntry from inputs and context."""
    audit_ctx = _normalize_context(ctx)

    if actor_override:
        if "actor_id" in actor_override:
            audit_ctx.actor_id = actor_override["actor_id"]
        if "actor_role" in actor_override:
            audit_ctx.actor_role = actor_override["actor_role"]
        if "actor_email" in actor_override:
            audit_ctx.actor_email = actor_override["actor_email"]
        if "actor_name" in actor_override:
            audit_ctx.actor_name = actor_override["actor_name"]

    resolved_category = category or category_for_action(action)
    sanitized_metadata = redact_and_bound_metadata(metadata)

    # Truncate strings to schema maximums
    clean_reason = (reason[:500] if reason else None)
    clean_error = (error_message[:500] if error_message else None)
    clean_target_id = str(target_id)[:255] if target_id is not None else None
    clean_target_label = str(target_label)[:255] if target_label is not None else None
    clean_target_type = str(target_type)[:64] if target_type is not None else None

    return AuditEntry(
        actor_id=audit_ctx.actor_id,
        actor_role=audit_ctx.actor_role,
        actor_email=audit_ctx.actor_email,
        actor_name=audit_ctx.actor_name,
        action=action[:64],
        category=resolved_category[:30],
        target_type=clean_target_type,
        target_id=clean_target_id,
        target_label=clean_target_label,
        reason=clean_reason,
        metadata=sanitized_metadata,
        ip=audit_ctx.ip,
        user_agent=audit_ctx.user_agent,
        device=audit_ctx.device,
        country=audit_ctx.country,
        status=status,
        error_message=clean_error,
    )


def _write_audit(entry: AuditEntry) -> str:
    """Internal database insert helper."""
    return _repo.insert(entry)


def record_audit(
    ctx: Optional[Union[AuditContext, Request, dict[str, Any]]],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[Any] = None,
    target_label: Optional[str] = None,
    reason: Optional[str] = None,
    metadata: Optional[Any] = None,
    status: AuditStatus = AuditStatus.SUCCESS,
    error_message: Optional[str] = None,
    category: Optional[str] = None,
    actor_override: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Record an audit log entry.
    
    GUARANTEE: NEVER THROWS.
    Catches all internal errors and logs a warning so logging failures can never
    take down or disrupt primary application workflows.
    """
    try:
        entry = _compose_entry(
            ctx=ctx,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            reason=reason,
            metadata=metadata,
            status=status,
            error_message=error_message,
            category=category,
            actor_override=actor_override,
        )
        return _write_audit(entry)
    except Exception as e:
        logger.warning("Failed to write audit log for action '%s': %s", action, str(e), exc_info=True)
        return None


def record_audit_strict(
    ctx: Optional[Union[AuditContext, Request, dict[str, Any]]],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[Any] = None,
    target_label: Optional[str] = None,
    reason: Optional[str] = None,
    metadata: Optional[Any] = None,
    status: AuditStatus = AuditStatus.SUCCESS,
    error_message: Optional[str] = None,
    category: Optional[str] = None,
    actor_override: Optional[dict[str, Any]] = None,
) -> str:
    """Record an audit log entry synchronously and THROW on failure.
    
    Use ONLY when the log entry is a strict prerequisite before handing a credential,
    session token, or sensitive secret to the client. If logging fails, the operation
    must fail closed.
    """
    entry = _compose_entry(
        ctx=ctx,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        reason=reason,
        metadata=metadata,
        status=status,
        error_message=error_message,
        category=category,
        actor_override=actor_override,
    )
    return _write_audit(entry)
