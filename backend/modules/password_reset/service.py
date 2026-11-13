"""Forgot Password workflow (NEXORA MEDIQ Phase 6F).

Security properties, each mapped to the specific requirement in the
Phase 6 authorization's S7:
  - Never reveals whether an account/email exists: request_reset() always
    returns the same generic result regardless of whether the email
    matched a user, is inactive, or doesn't exist at all.
  - Cryptographically secure, single-use token: secrets.token_urlsafe(32)
    (256 bits), never stored raw -- only its SHA-256 hash. A token can
    therefore never be recovered from the database, even by someone with
    read access to it.
  - Short-lived: RESET_TOKEN_EXPIRE_MINUTES (default 30).
  - Rate-limited: MAX_REQUESTS_PER_WINDOW per user per RATE_LIMIT_WINDOW_
    MINUTES, counted from rows already written (repository.
    count_recent_requests), not an in-memory counter -- holds across
    process restarts and multiple backend workers.
  - Password strength validated server-side (validate_password_strength),
    never trusting a frontend-only check.
  - No hardcoded OTP, no security questions: a signed, hashed, expiring,
    single-use token is the entire mechanism.
  - Reset tokens and plaintext passwords are never logged or audited --
    see the audit calls in controller.py, which record only user_id/email
    presence, never the token or password values.
  - Existing sessions revoked on successful reset: repository.
    invalidate_all_for_user() clears every still-outstanding token, and
    UserRepository.clear_active_session(user_id) drops active_session_id
    so any JWT minted before the reset is rejected on its next request by
    dependencies.auth._enforce_active_session (the same mechanism behind
    this app's existing single-active-session feature).

Email delivery: see send_reset_email() below. No general-purpose
transactional email sender exists in this codebase today (doc 28A S3.5) --
this is deliberately a clearly-labeled stub, not a silent no-op pretending
to work, per the authorization's explicit instruction not to pretend
email delivery works when the infrastructure for it doesn't exist yet.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt

from repositories.user_repository import UserRepository
from . import repository

logger = logging.getLogger(__name__)

RESET_TOKEN_EXPIRE_MINUTES = 30
RATE_LIMIT_WINDOW_MINUTES = 60
MAX_REQUESTS_PER_WINDOW = 3

GENERIC_REQUEST_RESULT = {
    "message": "If an account exists for that email address, a password reset link has been sent."
}


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def validate_password_strength(password: str) -> str | None:
    """Returns an error message, or None if the password is acceptable.
    Server-side check -- the frontend may additionally validate, but this
    is the one that actually governs whether a reset succeeds."""
    if not password or len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Za-z]", password):
        return "Password must include at least one letter."
    if not re.search(r"[0-9]", password):
        return "Password must include at least one number."
    return None


def send_reset_email(email: str, username: str, raw_token: str) -> bool:
    """STUB: no transactional email sender exists in this codebase yet
    (doc 28A S3.5 -- the only SMTP code is modules/sync's tightly-coupled
    store<->HO sync-package transport, not reusable for a user-facing
    email). This function deliberately does not send anything and
    returns False, so request_reset() can tell the caller plainly that
    delivery did not happen, rather than claiming success.

    To wire real delivery: implement SMTP send here (stdlib smtplib +
    STARTTLS, following the pattern in
    modules/sync/file_transfer_transport/email.py's _send(), with its own
    host/port/from-address/credentials read from environment variables --
    never hardcoded) and return True on confirmed send. The raw_token
    argument is already exactly what the email body's reset link needs
    (`https://<app-host>/reset-password?token=<raw_token>`); nothing else
    about request_reset()'s security properties needs to change for a
    real sender to be plugged in here.
    """
    logger.info(
        "password_reset: email delivery not configured (stub) -- "
        "reset requested for a user whose email ends in %s",
        email[-12:] if email else "?",
    )
    return False


def request_reset(email: str, request_ip: str | None = None) -> dict:
    """Always returns GENERIC_REQUEST_RESULT's shape. Never raises for an
    unknown/inactive email -- that is the whole point of the generic
    response. Returns an additional, internal-only `_debug` key when the
    account exists so the controller can decide whether to log/audit
    details that must never reach the HTTP response body itself."""
    email = (email or "").strip()
    if not email:
        return dict(GENERIC_REQUEST_RESULT)

    row = repository.get_user_by_email(email)
    if not row:
        return dict(GENERIC_REQUEST_RESULT)

    user_id, username, user_email, is_active = str(row[0]), row[1], row[2], bool(row[3])
    if not is_active:
        return dict(GENERIC_REQUEST_RESULT)

    window_start = datetime.now(timezone.utc) - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
    if repository.count_recent_requests(user_id, window_start) >= MAX_REQUESTS_PER_WINDOW:
        # Rate-limited: still the generic response. A real account that
        # has already requested 3 resets this hour gets no different an
        # answer than one that doesn't exist -- the limit is enforced
        # silently, not surfaced as a distinguishing signal.
        return dict(GENERIC_REQUEST_RESULT)

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)
    repository.create_token(user_id, token_hash, expires_at, request_ip)

    delivered = send_reset_email(user_email, username, raw_token)

    result = dict(GENERIC_REQUEST_RESULT)
    result["_internal"] = {"user_id": user_id, "username": username, "delivered": delivered}
    return result


def confirm_reset(raw_token: str, new_password: str) -> tuple[bool, str | None, str | None]:
    """Returns (success, error_message, user_id). error_message is always a
    safe, generic string -- never reveals which specific condition failed
    (expired vs. already-used vs. never-existed) to avoid giving an
    attacker a token-guessing oracle. user_id is returned on success only,
    purely so the caller can attribute the audit entry correctly -- it is
    never part of the HTTP response."""
    strength_error = validate_password_strength(new_password)
    if strength_error:
        return False, strength_error, None

    token_hash = _hash_token(raw_token or "")
    row = repository.get_valid_token(token_hash)
    if not row:
        return False, "This reset link is invalid or has expired. Please request a new one.", None

    token_id, user_id, _expires_at, _used_at = row[0], str(row[1]), row[2], row[3]

    password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    repository.update_password_hash(user_id, password_hash)
    repository.mark_used(token_id)
    repository.invalidate_all_for_user(user_id)
    UserRepository().clear_active_session(user_id)

    return True, None, user_id
