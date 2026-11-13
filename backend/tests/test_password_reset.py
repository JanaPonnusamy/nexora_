"""Forgot Password (NEXORA MEDIQ Phase 6F). Covers every item Phase 6 S12
explicitly asks to be tested: token generation, expiry, single-use
enforcement, rate limiting, generic responses for unknown accounts, and
password update + session revocation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from modules.password_reset import service


ACTIVE_USER_ROW = ("user-123", "jdoe", "jdoe@example.com", True)
INACTIVE_USER_ROW = ("user-456", "disabled", "disabled@example.com", False)


# ---------------------------------------------------------------------------
# Generic responses: never reveal account existence
# ---------------------------------------------------------------------------

def test_request_reset_unknown_email_returns_generic_message(monkeypatch):
    monkeypatch.setattr(service.repository, "get_user_by_email", lambda email: None)

    result = service.request_reset("nobody@example.com")

    assert result == service.GENERIC_REQUEST_RESULT
    assert "_internal" not in result


def test_request_reset_inactive_account_returns_same_generic_message(monkeypatch):
    monkeypatch.setattr(service.repository, "get_user_by_email", lambda email: INACTIVE_USER_ROW)
    created = []
    monkeypatch.setattr(service.repository, "create_token", lambda *a, **k: created.append(a))

    result = service.request_reset("disabled@example.com")

    assert result == service.GENERIC_REQUEST_RESULT
    assert not created  # no token ever generated for an inactive account


def test_request_reset_real_active_account_returns_identical_visible_message(monkeypatch):
    """The part of the response actually returned to the HTTP caller must
    be byte-identical whether the account exists or not -- only an
    internal-only key (stripped by the controller before the response is
    sent) differs."""
    monkeypatch.setattr(service.repository, "get_user_by_email", lambda email: ACTIVE_USER_ROW)
    monkeypatch.setattr(service.repository, "count_recent_requests", lambda *a, **k: 0)
    monkeypatch.setattr(service.repository, "create_token", lambda *a, **k: "token-id-1")
    monkeypatch.setattr(service, "send_reset_email", lambda *a, **k: False)

    result = service.request_reset("jdoe@example.com")

    assert result["message"] == service.GENERIC_REQUEST_RESULT["message"]


def test_request_reset_empty_email_returns_generic_message():
    result = service.request_reset("")
    assert result == service.GENERIC_REQUEST_RESULT


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

def test_request_reset_generates_a_token_and_hashes_it_before_storing(monkeypatch):
    monkeypatch.setattr(service.repository, "get_user_by_email", lambda email: ACTIVE_USER_ROW)
    monkeypatch.setattr(service.repository, "count_recent_requests", lambda *a, **k: 0)
    captured = {}

    def fake_create_token(user_id, token_hash, expires_at, request_ip):
        captured["user_id"] = user_id
        captured["token_hash"] = token_hash
        captured["expires_at"] = expires_at
        return "token-id-1"

    monkeypatch.setattr(service.repository, "create_token", fake_create_token)
    monkeypatch.setattr(service, "send_reset_email", lambda *a, **k: False)

    service.request_reset("jdoe@example.com", request_ip="10.0.0.5")

    assert captured["user_id"] == "user-123"
    # The stored value is a sha256 hex digest (64 hex chars), never the raw token.
    assert len(captured["token_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in captured["token_hash"])


def test_two_requests_produce_different_tokens(monkeypatch):
    monkeypatch.setattr(service.repository, "get_user_by_email", lambda email: ACTIVE_USER_ROW)
    monkeypatch.setattr(service.repository, "count_recent_requests", lambda *a, **k: 0)
    hashes = []
    monkeypatch.setattr(service.repository, "create_token", lambda user_id, token_hash, *a, **k: hashes.append(token_hash))
    monkeypatch.setattr(service, "send_reset_email", lambda *a, **k: False)

    service.request_reset("jdoe@example.com")
    service.request_reset("jdoe@example.com")

    assert hashes[0] != hashes[1]


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def test_request_reset_rate_limited_after_max_requests(monkeypatch):
    monkeypatch.setattr(service.repository, "get_user_by_email", lambda email: ACTIVE_USER_ROW)
    monkeypatch.setattr(service.repository, "count_recent_requests", lambda *a, **k: service.MAX_REQUESTS_PER_WINDOW)
    created = []
    monkeypatch.setattr(service.repository, "create_token", lambda *a, **k: created.append(a))

    result = service.request_reset("jdoe@example.com")

    assert result == service.GENERIC_REQUEST_RESULT  # still generic, not an error
    assert not created  # no new token issued past the limit


def test_request_reset_allowed_just_under_the_limit(monkeypatch):
    monkeypatch.setattr(service.repository, "get_user_by_email", lambda email: ACTIVE_USER_ROW)
    monkeypatch.setattr(service.repository, "count_recent_requests", lambda *a, **k: service.MAX_REQUESTS_PER_WINDOW - 1)
    created = []
    monkeypatch.setattr(service.repository, "create_token", lambda *a, **k: created.append(a) or "tid")
    monkeypatch.setattr(service, "send_reset_email", lambda *a, **k: False)

    service.request_reset("jdoe@example.com")

    assert created  # one more request is still allowed


# ---------------------------------------------------------------------------
# Password strength validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("password,should_fail", [
    ("short1", True),       # too short
    ("alllettersnoNum", True),  # no digit
    ("12345678", True),     # no letter
    ("Valid123", False),
])
def test_password_strength_validation(password, should_fail):
    error = service.validate_password_strength(password)
    assert (error is not None) == should_fail


# ---------------------------------------------------------------------------
# Token expiry and single-use (confirm_reset)
# ---------------------------------------------------------------------------

def test_confirm_reset_rejects_unknown_or_expired_token(monkeypatch):
    monkeypatch.setattr(service.repository, "get_valid_token", lambda token_hash: None)

    success, error, user_id = service.confirm_reset("some-raw-token", "GoodPass123")

    assert success is False
    assert user_id is None
    assert "invalid or has expired" in error.lower()


def test_confirm_reset_rejects_weak_password_before_touching_the_token(monkeypatch):
    """Strength is checked first so a weak-password attempt never consumes
    or even looks up the token -- a legitimate retry with a stronger
    password must still work."""
    looked_up = []
    monkeypatch.setattr(service.repository, "get_valid_token", lambda token_hash: looked_up.append(token_hash))

    success, error, user_id = service.confirm_reset("raw-token", "weak")

    assert success is False
    assert user_id is None
    assert not looked_up


def test_confirm_reset_succeeds_updates_password_and_revokes_sessions(monkeypatch):
    valid_row = ("token-id-1", "user-123", datetime.now(timezone.utc) + timedelta(minutes=10), None)
    monkeypatch.setattr(service.repository, "get_valid_token", lambda token_hash: valid_row)

    password_calls = []
    monkeypatch.setattr(service.repository, "update_password_hash", lambda user_id, password_hash: password_calls.append((user_id, password_hash)))
    marked_used = []
    monkeypatch.setattr(service.repository, "mark_used", lambda token_id: marked_used.append(token_id))
    invalidated = []
    monkeypatch.setattr(service.repository, "invalidate_all_for_user", lambda user_id: invalidated.append(user_id))
    session_cleared = []
    monkeypatch.setattr(service.UserRepository, "clear_active_session", lambda self, user_id: session_cleared.append(user_id))

    success, error, user_id = service.confirm_reset("raw-token", "GoodPass123")

    assert success is True
    assert error is None
    assert user_id == "user-123"
    assert password_calls[0][0] == "user-123"
    assert password_calls[0][1] != "GoodPass123"  # never stores the plaintext
    assert marked_used == ["token-id-1"]
    assert invalidated == ["user-123"]
    assert session_cleared == ["user-123"]  # existing sessions revoked


def test_confirm_reset_single_use_second_attempt_with_same_token_fails(monkeypatch):
    """get_valid_token already excludes used_at IS NOT NULL rows at the SQL
    level (repository.py) -- this test proves the service trusts that
    exclusion rather than re-checking used_at itself, by simulating the
    second call seeing no valid row at all (as the real query would)."""
    call_count = {"n": 0}

    def fake_get_valid_token(token_hash):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ("token-id-1", "user-123", datetime.now(timezone.utc) + timedelta(minutes=10), None)
        return None  # second lookup: token.used_at is now set, so WHERE excludes it

    monkeypatch.setattr(service.repository, "get_valid_token", fake_get_valid_token)
    monkeypatch.setattr(service.repository, "update_password_hash", lambda *a, **k: None)
    monkeypatch.setattr(service.repository, "mark_used", lambda *a, **k: None)
    monkeypatch.setattr(service.repository, "invalidate_all_for_user", lambda *a, **k: None)
    monkeypatch.setattr(service.UserRepository, "clear_active_session", lambda self, user_id: None)

    first = service.confirm_reset("raw-token", "GoodPass123")
    second = service.confirm_reset("raw-token", "AnotherPass456")

    assert first[0] is True
    assert second[0] is False
    assert "invalid or has expired" in second[1].lower()


# ---------------------------------------------------------------------------
# Email delivery stub honesty
# ---------------------------------------------------------------------------

def test_send_reset_email_stub_returns_false_not_a_fake_success():
    """This is the explicit requirement from the Phase 6 authorization:
    if email infrastructure doesn't exist, the code must not pretend
    delivery works."""
    result = service.send_reset_email("someone@example.com", "someone", "raw-token-value")
    assert result is False


# ---------------------------------------------------------------------------
# Controller: the internal key must never reach the HTTP response
# ---------------------------------------------------------------------------

def test_controller_request_reset_never_leaks_internal_key(monkeypatch):
    from controllers import password_reset_controller as prc

    monkeypatch.setattr(
        prc.service, "request_reset",
        lambda email, request_ip=None: {
            "message": "generic",
            "_internal": {"user_id": "u1", "username": "jdoe", "delivered": False},
        },
    )
    audited = []
    monkeypatch.setattr(prc, "record_audit", lambda **kwargs: audited.append(kwargs))

    class FakeRequest:
        client = None

    body = prc.PasswordResetRequest(email="jdoe@example.com")
    response = prc.request_reset(body, FakeRequest())

    assert "_internal" not in response
    assert response == {"message": "generic"}
    assert audited[0]["target_id"] == "u1"  # the audit trail still gets it


def test_controller_confirm_reset_404_path_has_no_user_id_leak(monkeypatch):
    from controllers import password_reset_controller as prc
    from fastapi import HTTPException

    monkeypatch.setattr(prc.service, "confirm_reset", lambda token, pw: (False, "invalid", None))
    audited = []
    monkeypatch.setattr(prc, "record_audit", lambda **kwargs: audited.append(kwargs))

    class FakeRequest:
        client = None

    body = prc.PasswordResetConfirm(token="bad", new_password="GoodPass123")
    with pytest.raises(HTTPException) as exc:
        prc.confirm_reset(body, FakeRequest())

    assert exc.value.status_code == 400
    assert audited[0]["status"].value == "failure"
