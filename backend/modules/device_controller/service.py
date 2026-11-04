"""Device Controller business logic: signed commands, the device inbox
(long-poll), remote terminal sessions, enrollment and the package catalog."""
from __future__ import annotations

import asyncio
import re
import secrets
import threading
import time
import uuid
from collections import defaultdict

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from modules.device_controller import packages, protocol, repository, signing

COMMAND_TTL_SECONDS = 30 * 60
UPDATE_TTL_SECONDS = 2 * 60 * 60
TERMINAL_TTL_SECONDS = 10 * 60
MAX_TERMINALS_PER_DEVICE = 5
MAX_INPUT_CHARS = 20000

# Long-poll pacing. The backend opens a fresh DB connection per query (no
# pool), so waiters watch an in-process change counter and only hit the DB on
# a change made through THIS node or every DB_RECHECK seconds (changes made
# through another HO node sharing the database).
_POLL_TICK = 0.25
_DB_RECHECK = 3.0

_changes = defaultdict(int)
_changes_lock = threading.Lock()


def _bump(key: str):
    with _changes_lock:
        _changes[key] += 1


def _version(key: str) -> int:
    return _changes.get(key, 0)


async def _wait_for(key: str, wait_seconds: float, fetch):
    """Call `fetch` (sync, in the threadpool) until it returns something truthy
    or `wait_seconds` passes. Re-queries on a local change or every
    _DB_RECHECK seconds."""
    deadline = time.monotonic() + max(0.0, min(wait_seconds, 30.0))
    seen = None
    next_db = 0.0
    while True:
        now = time.monotonic()
        current = _version(key)
        if current != seen or now >= next_db:
            seen = current
            next_db = now + _DB_RECHECK
            result = await run_in_threadpool(fetch)
            if result:
                return result
        if now >= deadline:
            return None
        await asyncio.sleep(_POLL_TICK)


def _device_key(device_id):
    return f"dev:{str(device_id).lower()}"


def _session_key(session_id):
    return f"term:{str(session_id).lower()}"


def _sign_payload(payload: dict) -> str:
    return protocol.sign(signing.private_key_pem(), payload)


def _base_payload(kind, device_id, ttl, message_id=None):
    now = int(time.time())
    return {
        "v": protocol.PROTOCOL_VERSION,
        "kind": kind,
        "id": message_id or str(uuid.uuid4()),
        "device_id": str(device_id).lower(),
        "issued_at": now,
        "expires_at": now + ttl,
    }


def _require_device(device_id):
    device = repository.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.get("registration_status") != "active":
        raise HTTPException(status_code=409, detail="Device registration is revoked")
    return device


# ---- package catalog ------------------------------------------------------

def list_packages():
    packages.sync_local_packages()
    grouped = {}
    for row in repository.list_packages():
        row["source_urls"] = [u for u in (row.get("source_urls") or "").split(",") if u]
        grouped.setdefault(row["app_key"], []).append(row)
    return {"packages": grouped, "has_command_key": signing.has_private_key()}


def _package_args(app_key, version):
    packages.sync_local_packages()
    pkg = repository.get_package(app_key, version)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"No {app_key} package {version} is published")
    return {
        "version": pkg["version"],
        "file_name": pkg["file_name"],
        "sha256": pkg["sha256"].strip().lower(),
        "file_size": int(pkg["file_size"]),
        "signature": pkg.get("signature"),
        "sources": [u for u in (pkg.get("source_urls") or "").split(",") if u],
    }


def package_file(app_key, version):
    found = packages.ensure_local(app_key, version)
    if not found:
        raise HTTPException(status_code=404, detail="Package not held by this HO node")
    return found


# ---- commands -------------------------------------------------------------

# A local absolute Windows folder, e.g. D:\NexoraStoreAgent (no UNC, no ..).
_SAFE_DIR = re.compile(r"^[A-Za-z]:\\(?!.*\.\.)[\w .()\\-]{1,200}$")

def _clean_args(app_key, action, args):
    args = dict(args or {})
    clean = {}
    if action in ("update", "install"):
        version = str(args.get("version") or "").strip()
        if not version:
            raise HTTPException(status_code=400, detail=f"{action} needs a version")
        clean["package"] = _package_args(app_key, version)
        if action == "install" and args.get("install_dir"):
            install_dir = str(args["install_dir"]).strip()
            if not _SAFE_DIR.match(install_dir):
                raise HTTPException(status_code=400, detail=f"Invalid install folder: {install_dir}")
            clean["install_dir"] = install_dir
    elif action == "set_ho_urls":
        urls = [str(u).strip().rstrip("/") for u in (args.get("urls") or []) if str(u).strip()]
        if not urls:
            raise HTTPException(status_code=400, detail="set_ho_urls needs at least one URL")
        for u in urls:
            if not (u.startswith("http://") or u.startswith("https://")) or len(u) > 300:
                raise HTTPException(status_code=400, detail=f"Invalid HO URL: {u}")
        clean["urls"] = urls[:10]
        clean["restart"] = bool(args.get("restart", True))
    elif action == "pause":
        try:
            minutes = int(args.get("minutes") or protocol.DEFAULT_PAUSE_MINUTES)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="pause minutes must be a number")
        clean["minutes"] = max(1, min(minutes, 24 * 60))
    return clean


def create_command(device_id, app_key, action, args, actor):
    if app_key not in protocol.APP_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown app '{app_key}'")
    if action not in protocol.APP_ACTIONS[app_key]:
        raise HTTPException(status_code=400, detail=f"'{action}' is not supported for {app_key}")
    _require_device(device_id)
    clean = _clean_args(app_key, action, args)

    ttl = UPDATE_TTL_SECONDS if action in ("update", "install") else COMMAND_TTL_SECONDS
    payload = _base_payload(protocol.KIND_COMMAND, device_id, ttl)
    payload.update({"app": app_key, "action": action, "args": clean, "issued_by": actor})
    signature = _sign_payload(payload)

    command = repository.insert_command(
        payload["id"], device_id, app_key, action, clean, payload, signature,
        actor, payload["expires_at"],
    )
    desired = protocol.DESIRED_FOR_ACTION.get(action)
    if desired:
        repository.set_desired(device_id, app_key, desired,
                               clean.get("minutes") if action == "pause" else None, actor)
    _bump(_device_key(device_id))
    return command


def create_bulk(device_ids, app_key, action, args, actor):
    results = []
    for device_id in device_ids:
        try:
            results.append({"device_id": device_id, "ok": True,
                            "command": create_command(device_id, app_key, action, args, actor)})
        except HTTPException as ex:
            results.append({"device_id": device_id, "ok": False, "error": ex.detail})
    return {"results": results}


def cancel_command(command_id, actor):
    if not repository.cancel_command(command_id, actor):
        raise HTTPException(status_code=409, detail="Only a QUEUED command can be cancelled")
    return repository.get_command(command_id)


# ---- device-facing --------------------------------------------------------

def record_heartbeat(device_id, hb, observed_ip):
    repository.record_heartbeat(device_id, hb, observed_ip)
    repository.resume_expired_pauses(device_id)
    desired = repository.get_desired(device_id)
    return {
        "desired": {k: {"desired_state": v["desired_state"],
                        "paused_until": v["paused_until"].isoformat() if v.get("paused_until") else None}
                    for k, v in desired.items()},
        "server_time": int(time.time()),
    }


async def poll_messages(device_id, wait_seconds):
    messages = await _wait_for(_device_key(device_id), wait_seconds,
                               lambda: repository.take_messages(device_id))
    return {"messages": messages or []}


def command_result(device_id, command_id, status, exit_code, result_text):
    if status not in ("RUNNING", "SUCCEEDED", "FAILED"):
        raise HTTPException(status_code=400, detail="Invalid status")
    if not repository.record_command_result(device_id, command_id, status, exit_code, result_text):
        raise HTTPException(status_code=404, detail="Command not found for this device")
    return {"ok": True}


def terminal_output(device_id, session_id, chunks, closed, reason):
    if chunks and not repository.add_output(session_id, device_id, chunks):
        raise HTTPException(status_code=404, detail="Session not found for this device")
    if closed:
        repository.mark_session_closed(session_id, device_id, reason or "ended")
    _bump(_session_key(session_id))
    return {"ok": True}


# ---- enrollment -----------------------------------------------------------

def new_enroll_code(note, hours, max_uses, actor):
    hours = max(1, min(int(hours or 24), 24 * 30))
    max_uses = max(1, min(int(max_uses or 1), 500))
    # 10 chars from an unambiguous alphabet, grouped for reading over the phone.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(10))
    code = f"{raw[:5]}-{raw[5:]}"
    return repository.create_enroll_code(code, note, actor, hours, max_uses)


def enroll_with_code(body):
    from modules.device_identity import repository as device_repo

    code = (body.code or "").strip().upper()
    row = repository.consume_enroll_code(code)
    if not row:
        raise HTTPException(status_code=403, detail="Enrollment code is invalid, used up or expired")
    pseudo_user = {"sub": None, "username": f"enroll:{code}", "tenant_id": None, "store_id": None}
    device_id, is_new = device_repo.register_device(
        body.device_fingerprint, body.public_key, "ED25519", body.machine_name,
        "device_controller", body.app_version, pseudo_user,
    )
    return {"device_id": device_id, "is_new": is_new}


# ---- terminal (operator side) ---------------------------------------------

def open_terminal(device_id, actor):
    _require_device(device_id)
    if repository.count_active_sessions(device_id) >= MAX_TERMINALS_PER_DEVICE:
        raise HTTPException(status_code=409,
                            detail=f"This PC already has {MAX_TERMINALS_PER_DEVICE} open terminals")
    session_id = str(uuid.uuid4())
    payload = _base_payload(protocol.KIND_TERM_OPEN, device_id, TERMINAL_TTL_SECONDS, session_id)
    payload.update({"session_id": session_id, "opened_by": actor})
    session = repository.create_session(session_id, device_id, payload, _sign_payload(payload), actor)
    _bump(_device_key(device_id))
    return session


def _require_session(session_id, live=True):
    session = repository.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Terminal session not found")
    if live and session["status"] not in ("OPENING", "OPEN"):
        raise HTTPException(status_code=409, detail=f"Terminal session is {session['status']}")
    return session


def send_input(session_id, data, actor):
    session = _require_session(session_id)
    data = (data or "")[:MAX_INPUT_CHARS]
    payload = _base_payload(protocol.KIND_TERM_INPUT, session["device_id"], TERMINAL_TTL_SECONDS)
    payload.update({"session_id": session_id.lower(), "data": data})
    seq = repository.add_io(session_id, "IN", data, actor, payload, _sign_payload(payload))
    _bump(_device_key(session["device_id"]))
    _bump(_session_key(session_id))
    return {"seq": seq}


def reset_terminal(session_id, actor):
    """Kill whatever is running and start a fresh PowerShell in the same tab."""
    session = _require_session(session_id)
    payload = _base_payload(protocol.KIND_TERM_RESET, session["device_id"], TERMINAL_TTL_SECONDS)
    payload.update({"session_id": session_id.lower()})
    repository.add_io(session_id, "IN", "<reset>", actor, payload, _sign_payload(payload))
    _bump(_device_key(session["device_id"]))
    return {"ok": True}


def close_terminal(session_id, actor):
    session = _require_session(session_id, live=False)
    if session["status"] in ("CLOSED", "FAILED"):
        return session
    payload = _base_payload(protocol.KIND_TERM_CLOSE, session["device_id"], TERMINAL_TTL_SECONDS)
    payload.update({"session_id": session_id.lower()})
    repository.request_close(session_id, payload, _sign_payload(payload), f"closed by {actor}")
    _bump(_device_key(session["device_id"]))
    _bump(_session_key(session_id))
    return repository.get_session(session_id)


async def terminal_output_after(session_id, after_seq, wait_seconds):
    def fetch():
        rows = repository.io_after(session_id, after_seq)
        return rows or None

    rows = await _wait_for(_session_key(session_id), wait_seconds, fetch)
    session = await run_in_threadpool(repository.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Terminal session not found")
    return {"rows": rows or [], "status": session["status"]}


def list_sessions(device_id=None, active_only=False):
    repository.close_stale_sessions()
    return {"sessions": repository.list_sessions(device_id, active_only)}
