"""Wire protocol shared by HO (signs) and the on-PC Device Controller (verifies).

Kept dependency-light on purpose (stdlib + modules.device_identity.crypto) so
the controller exe bundles it unchanged -- both sides MUST agree byte-for-byte
on what was signed.

Every HO -> device message is a JSON object with at least:
    v, kind, id, device_id, issued_at, expires_at
signed as canonical JSON (sorted keys, no whitespace) with the HO command key
(Ed25519). The controller rejects a message whose signature, device_id, expiry
or id (replay) does not check out -- so even over plain HTTP nobody can inject
or replay a command or a terminal keystroke.
"""
from __future__ import annotations

import base64
import json

PROTOCOL_VERSION = 1

# Message kinds HO sends to a device.
KIND_COMMAND = "command"
KIND_TERM_OPEN = "term_open"
KIND_TERM_INPUT = "term_input"
KIND_TERM_RESET = "term_reset"
KIND_TERM_CLOSE = "term_close"

# Apps the controller manages, and what each accepts. "controller" is the
# controller itself (self-update / restart / legacy-watchdog retirement).
APP_ACTIONS = {
    "store_agent": {"start", "stop", "restart", "pause", "resume", "update", "install", "set_ho_urls"},
    "mail_transfer": {"start", "stop", "restart", "pause", "resume"},
    "stock_client": {"start", "stop", "restart", "pause", "resume", "update", "install"},
    "ho_backend": {"start", "stop", "restart", "pause", "resume", "update"},
    "controller": {"update", "restart", "retire_legacy_watchdogs"},
}

APP_LABELS = {
    "store_agent": "Store Agent",
    "mail_transfer": "Mail Transfer",
    "stock_client": "Stock Client",
    "ho_backend": "HO Backend",
    "controller": "Device Controller",
}

# Actions that change the persisted desired run-state (the controller keeps
# enforcing it every cycle, which is what replaces the old watchdogs).
DESIRED_FOR_ACTION = {
    "start": "RUNNING",
    "restart": "RUNNING",
    "resume": "RUNNING",
    "stop": "STOPPED",
    "pause": "PAUSED",
}

DEFAULT_PAUSE_MINUTES = 30


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sign(private_pem: str, payload: dict) -> str:
    from modules.device_identity import crypto

    return base64.b64encode(crypto.sign(private_pem, canonical(payload))).decode("ascii")


def verify(public_pem: str, payload: dict, signature_b64: str) -> bool:
    from modules.device_identity import crypto

    try:
        sig = base64.b64decode(signature_b64 or "")
    except Exception:
        return False
    return crypto.verify(public_pem, canonical(payload), sig)


def release_manifest(version: str, sha256: str, size: int) -> bytes:
    """The bytes a RELEASE package signature covers (same convention as the
    stock-client / HO-backend publish scripts)."""
    return f"{version}|{sha256}|{size}".encode("utf-8")
