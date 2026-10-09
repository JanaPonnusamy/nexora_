"""Crypto + envelope helpers for the Remote Order Agent contract.

Auth model (docs/02): the agent holds an opaque ``device_token`` (Bearer) and a
``device_secret`` used to HMAC-sign every request. HO looks the device up by the
token's hash, then recomputes the SAME secret to verify the signature.

The device_secret is DERIVED, never stored: ``HMAC_SHA256(server_key, "nmv-agent
-device-secret:" + device_id)``. The server key is the app's JWT secret, so no
new secret-at-rest is introduced and the secret is reproducible for verification
yet unguessable without the server key. Rotating a device = new device_id (new
row + new token), which yields a new secret and dead old credentials.

These functions are pure (no DB, no FastAPI) so they unit-test with fixed
vectors; the request dependency that uses them lives in ``router.py``.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from config.security import SECRET_KEY

_SECRET_PURPOSE = "nmv-agent-device-secret:"
# HO rejects a signature whose timestamp is more than this many seconds from now
# (replay bound). Mirrors the agent's documented 300 s skew window.
MAX_CLOCK_SKEW_SECONDS = 300


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def hmac_sha256_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def new_device_token() -> str:
    """A fresh opaque bearer token. Only its hash is stored server-side."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Stable lookup hash for a device token (never store the token itself)."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def derive_device_secret(device_id: str) -> str:
    """Reproducible per-device HMAC secret (see module docstring). Hex string."""
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        (_SECRET_PURPOSE + str(device_id)).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_canonical(ts: str, method: str, path_and_query: str, body: bytes) -> str:
    """The exact string both sides HMAC (HoClient.cs Send): ts, METHOD,
    path+query, and the hex sha256 of the body (empty body for GET)."""
    return "\n".join([str(ts), method.upper(), path_and_query, sha256_hex(body)])


def verify_signature(device_id: str, ts: str, method: str, path_and_query: str,
                     body: bytes, signature: str,
                     now: float | None = None) -> tuple[bool, str]:
    """Constant-time signature check + skew bound. Returns (ok, reason)."""
    try:
        ts_int = int(str(ts).strip())
    except (TypeError, ValueError):
        return False, "bad timestamp"
    now = time.time() if now is None else now
    if abs(now - ts_int) > MAX_CLOCK_SKEW_SECONDS:
        return False, "timestamp skew"
    expected = hmac_sha256_hex(derive_device_secret(device_id),
                               build_canonical(ts, method, path_and_query, body))
    if not signature or not hmac.compare_digest(expected, str(signature).strip().lower()):
        return False, "signature mismatch"
    return True, "ok"


# ---- response envelope ----------------------------------------------------

def envelope(store: dict, **extra) -> dict:
    """Every successful body carries ok + the device's own store identity; the
    agent rejects any response whose store_code/store_id is not its own."""
    body = {"ok": True, "store_code": store["store_code"], "store_id": store["store_id"]}
    body.update(extra)
    return body


def error_envelope(store: dict | None, code: str, message: str, retryable: bool = False) -> dict:
    body: dict = {"ok": False}
    if store:
        body["store_code"] = store.get("store_code")
        body["store_id"] = store.get("store_id")
    body["error"] = {"code": code, "message": message, "retryable": bool(retryable)}
    return body
