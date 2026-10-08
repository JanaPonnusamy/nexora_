"""One-time enrollment codes for NMV device bootstrap.

The problem this solves: the existing device-identity registration
(`POST /api/auth/device/register`) requires a signed-in store-user's bearer
token to authorise the machine. The NMV Settings app has no such login -- it has
an "Enrollment code" field and an "Enroll device" button. So HO must be able to
issue a one-time code that lets *this* NMV device register itself.

This is NOT a second authentication mechanism. A redeemed code does exactly what
`register` does -- it calls `device_identity.repository.register_device` with the
device's Ed25519 public key and auto-assigns the bound store -- and then mints a
device token using the *same* signer/claims as `device_identity.issue_token`.
The code only replaces the "a store user vouches for this machine" step with "an
HO super admin pre-authorised this one machine, once".

Security properties:
  * code is 160-bit cryptographically random (secrets);
  * only its SHA-256 hash is stored -- the plaintext is returned to the admin
    exactly once and never persisted or logged;
  * single-use (atomic conditional claim in the repository);
  * time-boxed (default 15 min, env-overridable);
  * bound to one store_id -- a code issued for NMV can never enroll any other
    store, no matter what store_code the client sends;
  * presentations are counted and a code locks after too many attempts.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets

from config.security import EXPIRE_MINUTES, create_access_token
from modules.device_identity import repository as device_repo
from modules.nmv_integration import audit_service, repository
from modules.nmv_integration.exceptions import EnrollmentFailed, EnrollmentRateLimited

# Lifetime of a freshly issued code. 15 minutes is long enough to walk a code
# over to the store PC and type it, short enough to bound exposure.
ENROLLMENT_TTL_SECONDS = int(os.getenv("NMV_ENROLLMENT_TTL_SECONDS", "900"))
_TTL_MIN, _TTL_MAX = 300, 86_400

# A known code locks after this many presentations (defence in depth; the code's
# 160-bit entropy already makes blind guessing infeasible).
MAX_ENROLL_ATTEMPTS = int(os.getenv("NMV_ENROLLMENT_MAX_ATTEMPTS", "10"))

_DEFAULT_APP_TYPE = "nmv_agent"
# Deliberately generic so a failed attempt is not an oracle for *why* it failed.
_FAIL_MESSAGE = "Invalid or expired enrollment code."


# ---- code primitives ------------------------------------------------------

def _new_code() -> str:
    """A fresh 160-bit code, base32-encoded and hyphen-grouped for typing.

    e.g. 'K7Q2-9ZB4-...'. 20 random bytes -> 32 base32 chars.
    """
    raw = secrets.token_bytes(20)
    body = base64.b32encode(raw).decode("ascii").rstrip("=")
    return "-".join(body[i:i + 4] for i in range(0, len(body), 4))


def _normalise(code: str) -> str:
    """Canonical form for hashing: uppercase, letters/digits only (so the user
    may type it with or without the grouping hyphens / surrounding spaces)."""
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


def _hash_code(code: str) -> str:
    return hashlib.sha256(_normalise(code).encode("ascii")).hexdigest()


def _bounded_ttl(ttl_seconds) -> int:
    if not ttl_seconds:
        return ENROLLMENT_TTL_SECONDS
    return max(_TTL_MIN, min(int(ttl_seconds), _TTL_MAX))


# ---- admin: generate ------------------------------------------------------

def generate_enrollment_code(store, admin_user, ttl_seconds=None):
    """Issue a one-time code bound to `store`. Returns the plaintext code ONCE.

    The caller (router) has already validated the store exists and is active and
    that the caller is an HO super admin.
    """
    repository.ensure_enrollment_schema()
    ttl = _bounded_ttl(ttl_seconds)
    code_plain = _new_code()
    code_id, expires_at = repository.create_enrollment_code(
        store_id=store["store_id"],
        store_code=store["store_code"],
        code_hash=_hash_code(code_plain),
        ttl_seconds=ttl,
        created_by=(admin_user or {}).get("sub"),
        created_by_username=(admin_user or {}).get("username"),
    )
    # Audit the creation -- id, store, expiry only. The code itself is NEVER in
    # the metadata (and audit_service._safe would not catch a key named 'code',
    # so we simply never put it there).
    audit_service.record(
        "nmv.enrollment.generate", store["store_code"],
        target_id=code_id,
        metadata={"code_id": code_id, "expires_at": expires_at, "ttl_seconds": ttl},
    )
    return {
        "store_code": store["store_code"],
        "store_id": store["store_id"],
        "code_id": code_id,
        "enrollment_code": code_plain,
        "expires_at": expires_at,
        "expires_in_seconds": ttl,
    }


# ---- device: enroll -------------------------------------------------------

def enroll_device(store, body):
    """Redeem a code and bootstrap the device. Returns device_id + a ready
    device bearer token (one-step enrollment)."""
    repository.ensure_enrollment_schema()

    outcome = repository.redeem_enrollment_code(
        _hash_code(body.enrollment_code), store["store_id"], MAX_ENROLL_ATTEMPTS
    )
    status = outcome["status"]
    if status != "ok":
        code = outcome.get("code") or {}
        audit_service.record(
            "nmv.enroll", store["store_code"], ok=False, error=status,
            metadata={"code_id": code.get("id"), "result": status},
        )
        if status == "locked":
            raise EnrollmentRateLimited("Too many attempts; request a new enrollment code.")
        raise EnrollmentFailed(_FAIL_MESSAGE)

    code = outcome["code"]

    # Reuse the EXACT existing registration path. Passing store_id in the
    # synthetic user triggers device_identity's auto-assign of that store, and
    # the merge-by-fingerprint makes a re-enroll of the same machine idempotent
    # (rotates its key, reactivates). No second device model, no second table.
    enroll_user = {
        "sub": code.get("created_by"),            # the admin who authorised this machine
        "username": code.get("created_by_username") or "nmv-enrollment",
        "tenant_id": store["tenant_id"],
        "store_id": store["store_id"],            # -> auto-assign NMV
    }
    device_id, is_new = device_repo.register_device(
        body.device_fingerprint,
        body.public_key,
        body.key_algo or "ED25519",
        body.machine_name,
        body.app_type or _DEFAULT_APP_TYPE,
        body.app_version,
        enroll_user,
    )
    repository.attach_device_to_code(code["id"], device_id)

    # Mint a device token with the same claims/signer as device_identity's
    # signature flow, so the agent can sync immediately (one-step enrollment).
    stores = device_repo.get_assigned_stores_with_config(device_id)
    store_ids = [s["store_id"] for s in stores]
    tenant_ids = sorted({s["tenant_id"] for s in stores if s["tenant_id"]})
    device = device_repo.get_device(device_id) or {}
    device_repo.touch_last_seen(device_id)
    token = create_access_token({
        "sub": device_id,
        "token_kind": "device",
        "device_id": device_id,
        "app_type": device.get("app_type"),
        "store_ids": store_ids,
        "tenant_ids": tenant_ids,
    })

    audit_service.record(
        "nmv.enroll", store["store_code"], device_id,
        target_id=code["id"],
        metadata={"code_id": code["id"], "is_new_device": is_new,
                  "assigned_store_ids": store_ids},
    )
    return {
        "device_id": device_id,
        "store_code": store["store_code"],
        "assigned_store_ids": store_ids,
        "token": token,
        "token_type": "bearer",
        "expires_in_seconds": EXPIRE_MINUTES * 60,
    }
