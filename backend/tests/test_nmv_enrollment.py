"""Offline tests for the NMV one-time enrollment-code flow (nmv_integration).

No live DB: the repository + device-identity calls are mocked. Covers code
generation (plaintext returned once, only the hash stored), TTL bounding, the
redeem outcomes (ok / wrong_store / locked / used / expired / not_found), store
binding, that enrollment reuses the existing device_identity.register_device
(no second identity model), and that a device token is minted in one step.
"""
from __future__ import annotations

import pytest

from modules.nmv_integration import enrollment
from modules.nmv_integration.exceptions import EnrollmentFailed, EnrollmentRateLimited
from modules.nmv_integration.schemas import EnrollRequest

STORE_ID = "4A2CEFF0-13C5-484C-B263-DE297E1E23E3"
TENANT_ID = "bbbbbbbb-0000-0000-0000-000000000001"
STORE = {"store_id": STORE_ID, "store_code": "NMV", "tenant_id": TENANT_ID, "is_active": True}


# --------------------------------------------------------------------------
# code primitives
# --------------------------------------------------------------------------

def test_new_code_is_grouped_base32_and_high_entropy():
    code = enrollment._new_code()
    assert "-" in code                       # hyphen-grouped for typing
    norm = enrollment._normalise(code)
    assert norm.isalnum() and norm.isupper()
    assert len(norm) >= 28                    # 20 random bytes -> 32 base32 chars


def test_hash_is_hyphen_and_case_insensitive():
    # The operator may type the code with or without grouping hyphens / case.
    code = enrollment._new_code()
    assert enrollment._hash_code(code) == enrollment._hash_code(code.lower())
    assert enrollment._hash_code(code) == enrollment._hash_code(code.replace("-", ""))
    assert enrollment._hash_code(code) != enrollment._normalise(code)  # not plaintext


def test_bounded_ttl():
    assert enrollment._bounded_ttl(None) == enrollment.ENROLLMENT_TTL_SECONDS
    assert enrollment._bounded_ttl(10) == enrollment._TTL_MIN      # clamped up
    assert enrollment._bounded_ttl(10**9) == enrollment._TTL_MAX   # clamped down
    assert enrollment._bounded_ttl(1800) == 1800


# --------------------------------------------------------------------------
# generate: plaintext returned once, only the hash persisted, store-bound
# --------------------------------------------------------------------------

@pytest.fixture
def mock_generate(monkeypatch):
    captured = {}

    def fake_create(store_id, store_code, code_hash, ttl_seconds, created_by, created_by_username):
        captured.update(store_id=store_id, store_code=store_code, code_hash=code_hash,
                        ttl_seconds=ttl_seconds, created_by=created_by)
        return "code-id-1", "2026-10-08T12:00:00"

    monkeypatch.setattr(enrollment.repository, "ensure_enrollment_schema", lambda: None)
    monkeypatch.setattr(enrollment.repository, "create_enrollment_code", fake_create)
    monkeypatch.setattr(enrollment.audit_service, "record", lambda *a, **k: None)
    return captured


def test_generate_returns_plaintext_once_and_stores_only_hash(mock_generate):
    result = enrollment.generate_enrollment_code(STORE, {"sub": "admin-1", "username": "root"})
    code = result["enrollment_code"]
    assert code and isinstance(code, str)
    # what was persisted is the hash of exactly the returned code
    assert mock_generate["code_hash"] == enrollment._hash_code(code)
    # the plaintext itself was never passed to the store layer
    assert mock_generate["code_hash"] != code
    # bound to this store
    assert mock_generate["store_id"] == STORE_ID
    assert mock_generate["store_code"] == "NMV"
    assert result["code_id"] == "code-id-1"
    assert result["expires_in_seconds"] == enrollment.ENROLLMENT_TTL_SECONDS


# --------------------------------------------------------------------------
# enroll: happy path reuses device_identity.register_device + mints a token
# --------------------------------------------------------------------------

def _body(code="AAAA-BBBB-CCCC"):
    return EnrollRequest(
        enrollment_code=code, device_fingerprint="fp-1", public_key="PEM",
        key_algo="ED25519", machine_name="NMV-PC", app_type="nmv_agent", app_version="1.0",
    )


@pytest.fixture
def mock_enroll(monkeypatch):
    calls = {"register_user": None, "attach": None, "token_claims": None}

    def fake_register(fp, pub, algo, machine, app_type, app_version, user):
        calls["register_user"] = user
        return "device-123", True

    def fake_token(claims):
        calls["token_claims"] = claims
        return "DEVICE.JWT.TOKEN"

    monkeypatch.setattr(enrollment.repository, "ensure_enrollment_schema", lambda: None)
    monkeypatch.setattr(enrollment.repository, "attach_device_to_code",
                        lambda code_id, device_id: calls.update(attach=(code_id, device_id)))
    monkeypatch.setattr(enrollment.device_repo, "register_device", fake_register)
    monkeypatch.setattr(enrollment.device_repo, "get_assigned_stores_with_config",
                        lambda did: [{"store_id": STORE_ID, "tenant_id": TENANT_ID}])
    monkeypatch.setattr(enrollment.device_repo, "get_device", lambda did: {"app_type": "nmv_agent"})
    monkeypatch.setattr(enrollment.device_repo, "touch_last_seen", lambda did: None)
    monkeypatch.setattr(enrollment, "create_access_token", fake_token)
    monkeypatch.setattr(enrollment.audit_service, "record", lambda *a, **k: None)
    return calls


def _redeem_ok(monkeypatch):
    monkeypatch.setattr(
        enrollment.repository, "redeem_enrollment_code",
        lambda h, sid, maxa: {"status": "ok", "code": {
            "id": "c1", "store_id": STORE_ID, "store_code": "NMV",
            "created_by": "admin-1", "created_by_username": "root"}},
    )


def test_enroll_ok_registers_assigns_and_mints_token(monkeypatch, mock_enroll):
    _redeem_ok(monkeypatch)
    result = enrollment.enroll_device(STORE, _body())

    assert result["device_id"] == "device-123"
    assert result["store_code"] == "NMV"
    assert result["assigned_store_ids"] == [STORE_ID]
    assert result["token"] == "DEVICE.JWT.TOKEN"
    assert result["token_type"] == "bearer"

    # reused the EXISTING device-identity register path; store bound from the code
    assert mock_enroll["register_user"]["store_id"] == STORE_ID
    assert mock_enroll["attach"] == ("c1", "device-123")
    # the minted token is a device token scoped to the bound store
    claims = mock_enroll["token_claims"]
    assert claims["token_kind"] == "device"
    assert claims["device_id"] == "device-123"
    assert claims["store_ids"] == [STORE_ID]


# --------------------------------------------------------------------------
# enroll: rejection outcomes never register a device
# --------------------------------------------------------------------------

@pytest.mark.parametrize("status", ["wrong_store", "used", "expired", "not_found", "superseded", "consumed"])
def test_enroll_rejections_raise_generic_403(monkeypatch, mock_enroll, status):
    monkeypatch.setattr(
        enrollment.repository, "redeem_enrollment_code",
        lambda h, sid, maxa: {"status": status, "code": {"id": "c1"}},
    )
    with pytest.raises(EnrollmentFailed) as exc:
        enrollment.enroll_device(STORE, _body())
    # generic message -- not an oracle for which check failed
    assert str(exc.value.message) == enrollment._FAIL_MESSAGE
    assert mock_enroll["register_user"] is None  # no device ever registered


def test_enroll_locked_raises_rate_limited(monkeypatch, mock_enroll):
    monkeypatch.setattr(
        enrollment.repository, "redeem_enrollment_code",
        lambda h, sid, maxa: {"status": "locked", "code": {"id": "c1"}},
    )
    with pytest.raises(EnrollmentRateLimited):
        enrollment.enroll_device(STORE, _body())
    assert mock_enroll["register_user"] is None


def test_enroll_passes_store_id_to_redeem(monkeypatch, mock_enroll):
    """redeem is called with the server-resolved store_id, so a code issued for
    another store can never be redeemed here (wrong_store)."""
    seen = {}
    monkeypatch.setattr(
        enrollment.repository, "redeem_enrollment_code",
        lambda h, sid, maxa: seen.update(hash=h, store_id=sid, max_attempts=maxa)
        or {"status": "ok", "code": {"id": "c1", "store_id": STORE_ID,
                                     "created_by": None, "created_by_username": None}},
    )
    enrollment.enroll_device(STORE, _body(code="ZZZZ-1111"))
    assert seen["store_id"] == STORE_ID
    assert seen["hash"] == enrollment._hash_code("ZZZZ-1111")
    assert seen["max_attempts"] == enrollment.MAX_ENROLL_ATTEMPTS
