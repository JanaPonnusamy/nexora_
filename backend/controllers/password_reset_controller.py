
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from dtos.password_reset_request import PasswordResetConfirm, PasswordResetRequest
from modules.audit.models import AuditStatus
from modules.audit.writer import record_audit
from modules.password_reset import service

router = APIRouter(prefix="/api/auth/password-reset", tags=["Password Reset"])


@router.post("/request")
def request_reset(body: PasswordResetRequest, request: Request):
    """Public (no JWT -- a locked-out user has none). Always returns the
    same generic message regardless of whether the email matched an
    account, per Phase 6 S7's explicit requirement not to reveal account
    existence. Audited WITHOUT the raw token (never generated into this
    response in the first place) and without the email in the clear
    reason text where avoidable -- only enough to investigate abuse."""
    result = service.request_reset(body.email, request_ip=request.client.host if request.client else None)
    internal = result.pop("_internal", None)

    if internal:
        record_audit(
            ctx=request,
            action="auth.password_reset.requested",
            category="auth",
            target_type="user",
            target_id=internal["user_id"],
            target_label=internal["username"],
            status=AuditStatus.SUCCESS,
            reason=f"Password reset requested for user '{internal['username']}'",
            metadata={"email_delivered": internal["delivered"]},
            actor_override={"actor_name": internal["username"]},
        )
    else:
        # Deliberately low-detail: an unknown/inactive email must not be
        # distinguishable from a rate-limited one in the audit trail either,
        # beyond "a reset was requested for an email that didn't resolve to
        # an active account" -- the email itself IS recorded here (audit
        # logs are restricted to super admins, unlike the HTTP response),
        # since investigating a flood of bogus requests needs it.
        record_audit(
            ctx=request,
            action="auth.password_reset.requested",
            category="auth",
            target_type="email",
            target_label=body.email,
            status=AuditStatus.FAILURE,
            reason="Password reset requested for an email with no matching active account",
        )

    return result


@router.post("/confirm")
def confirm_reset(body: PasswordResetConfirm, request: Request):
    """Public (no JWT). Validates the token and password strength, updates
    the password, invalidates every outstanding reset token for that user,
    and revokes their existing session. Never logs the raw token or the
    new password anywhere -- only success/failure and, on success, which
    user_id changed."""
    success, error, user_id = service.confirm_reset(body.token, body.new_password)

    if not success:
        record_audit(
            ctx=request,
            action="auth.password_reset.confirm_failed",
            category="auth",
            target_type="password_reset_token",
            status=AuditStatus.FAILURE,
            error_message=error,
            reason="Password reset confirmation failed",
        )
        raise HTTPException(status_code=400, detail=error)

    record_audit(
        ctx=request,
        action="auth.password_reset.completed",
        category="auth",
        target_type="user",
        target_id=user_id,
        status=AuditStatus.SUCCESS,
        reason="Password reset completed; existing sessions revoked",
    )
    return {"message": "Your password has been reset. Please sign in with your new password."}
