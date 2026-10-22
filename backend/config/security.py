from __future__ import annotations

"""JWT issuing/verification for the NEXORA API.

UNINEX_JWT_SECRET must be set to a strong random value in production (HO
installer writes it into config\\ho.env alongside the DB settings). The
fallback below only exists so the app still runs from source in dev.
"""
import hashlib
import os
from datetime import datetime, timedelta, timezone

import jwt

SECRET_KEY = os.getenv("UNINEX_JWT_SECRET", "dev-only-insecure-secret-change-me")
ALGORITHM = "HS256"
SETUP_AUDIENCE = "store_agent_setup"
CONFIRMATION_AUDIENCE = "action_confirmation"
EXPIRE_MINUTES = int(os.getenv("UNINEX_JWT_EXPIRE_MINUTES", "720"))
SETUP_TOKEN_EXPIRE_MINUTES = int(os.getenv("UNINEX_SETUP_JWT_EXPIRE_MINUTES", "43200"))
CONFIRMATION_TOKEN_EXPIRE_MINUTES = int(os.getenv("UNINEX_CONFIRMATION_JWT_EXPIRE_MINUTES", "10"))


def create_access_token(claims: dict) -> str:
    payload = dict(claims)
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_setup_token(claims: dict) -> str:
    payload = dict(claims)
    payload["scope"] = "setup_readonly"
    payload.setdefault("aud", SETUP_AUDIENCE)
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=SETUP_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def setup_access_checksum(
    username: str,
    password: str,
    scope: str = "setup_readonly",
    audience: str = "store_agent_setup",
    allowed_paths: list[str] | tuple[str, ...] = (),
) -> str:
    payload = "|".join([username, password, scope, audience, *allowed_paths])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def decode_setup_token(token: str) -> dict:
    """Setup tokens carry an `aud` claim, so they must be decoded WITH the
    audience or PyJWT raises InvalidAudienceError. decode_access_token (used for
    normal bearer tokens, which have no `aud`) cannot validate them."""
    return jwt.decode(
        token, SECRET_KEY, algorithms=[ALGORITHM], audience=SETUP_AUDIENCE
    )


def create_confirmation_token(claims: dict) -> str:
    """Short-lived (default 10 min) signed token binding a client-visible
    preview to the exact server-computed state it previewed -- e.g. Legacy
    Order's Qty Check confirmation (store_name/order_id/count). The backend
    always re-derives the authoritative value independently and never trusts
    the token's claims as a substitute for that recheck; the token only
    proves the client actually saw the state it is now confirming, and that
    the confirmation can't be replayed stale (10-minute expiry) or forged
    (HMAC-signed, same secret/algorithm as every other access token)."""
    payload = dict(claims)
    payload["aud"] = CONFIRMATION_AUDIENCE
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=CONFIRMATION_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_confirmation_token(token: str) -> dict:
    return jwt.decode(
        token, SECRET_KEY, algorithms=[ALGORITHM], audience=CONFIRMATION_AUDIENCE
    )
