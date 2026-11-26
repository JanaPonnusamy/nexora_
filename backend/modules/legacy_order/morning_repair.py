"""Auto-repair for the morning auto order (owner request 2026-11-27): keep a
store's sync path healthy without anyone touching the store PC, through the
store PC's Device Controller (modules/device_controller -- the HO signs the
command, the controller runs it as SYSTEM):

  * prepare(): once a day, before the store's first sync, bring its Store
    Agent up to the current release (agent_ops' is_current release, else the
    newest store_agent package in the controller catalog). Never downgrades.
  * repair(): the sync failed, or the agent stopped beating --
      heartbeat live (agent up but its sync is stuck)  -> restart the agent,
                                                          then reinstall the
                                                          current release;
      no heartbeat (agent dead, PC up)                 -> update to the current
                                                          release (or restart
                                                          when already on it),
                                                          then reinstall.
    Each step runs at most once per store per day; the caller retries the
    order after a step that worked.

The Stock Client is not touched here: its releases go out through the
per-store rollout (modules/stock_client_ops), which this must not bypass.
"""
from __future__ import annotations

import datetime
import logging
import re
import time

from modules.legacy_order import database

logger = logging.getLogger(__name__)

AGENT = "store_agent"
ACTOR = "morning-auto-order"
COMMAND_WAIT_SECONDS = 15 * 60
HEARTBEAT_WAIT_SECONDS = 4 * 60
HEARTBEAT_FRESH_SECONDS = 120
_LIVE_COMMAND = ("QUEUED", "DELIVERED", "RUNNING")

# (day, database, STORE) -> {"prepared": bool, "steps": [step names done]}
_state: dict = {}


def _key(store_name):
    return (datetime.date.today(), database.active_database_name().upper(), store_name.strip().upper())


def _day_state(store_name):
    today = datetime.date.today()
    for k in [k for k in _state if k[0] != today]:
        _state.pop(k, None)
    return _state.setdefault(_key(store_name), {"prepared": False, "steps": []})


def _vkey(version):
    return tuple(int(n) for n in re.findall(r"\d+", str(version or "")))


def target_agent_version():
    """The release every store agent should run, or None if this HO's
    controller catalog holds no store_agent package."""
    from modules.device_controller import packages
    from modules.device_controller import repository as dc

    try:
        packages.sync_local_packages()
    except Exception:
        logger.debug("[MORNING_REPAIR] package scan failed", exc_info=True)
    held = [p["version"] for p in dc.list_packages() if p["app_key"] == AGENT]
    if not held:
        return None
    try:
        from modules.agent_ops import repository as agent_ops

        current = agent_ops.get_current_release()
        if current and current.get("version") in held:
            return current["version"]
    except Exception:
        logger.debug("[MORNING_REPAIR] no current agent release", exc_info=True)
    return max(held, key=_vkey)


def _store_id(store_name):
    sid = database.platform_store_id(store_name)
    return str(sid).lower() if sid else None


def store_devices(store_name):
    """Active controller devices assigned to this store: [(device, agent app
    snapshot or None)], online ones first."""
    from modules.device_controller import repository as dc

    sid = _store_id(store_name)
    if not sid:
        return []
    out = []
    for d in dc.list_devices():
        if d.get("registration_status") != "active":
            continue
        if not any(str(s.get("store_id") or "").lower() == sid for s in d.get("stores") or []):
            continue
        agent = next((a for a in d.get("apps") or [] if a.get("app_key") == AGENT and a.get("installed")), None)
        out.append((d, agent))
    out.sort(key=lambda pair: not pair[0].get("online"))
    return out


def _heartbeat_age(store_name):
    from modules.legacy_order import device_sync

    sid = _store_id(store_name)
    return device_sync._agent_heartbeat_age_seconds(sid) if sid else None


def _agent_alive(store_name):
    age = _heartbeat_age(store_name)
    return age is not None and age <= HEARTBEAT_FRESH_SECONDS


def _run(device, action, version=None):
    """Queue a signed controller command and wait for its result.
    Returns (ok, text)."""
    from modules.device_controller import repository as dc
    from modules.device_controller import service as dc_service

    args = {"version": version} if version else {}
    try:
        cmd = dc_service.create_command(device["device_id"], AGENT, action, args, ACTOR)
    except Exception as exc:  # HTTPException: no command key, package missing ...
        return False, f"{action} not sent: {getattr(exc, 'detail', None) or exc}"
    deadline = time.monotonic() + COMMAND_WAIT_SECONDS
    row = cmd
    while time.monotonic() < deadline:
        row = dc.get_command(cmd["command_id"]) or row
        if row.get("status") not in _LIVE_COMMAND:
            break
        time.sleep(5)
    status = row.get("status")
    text = (row.get("result_text") or "").strip().splitlines()
    detail = text[-1] if text else status
    return status == "SUCCEEDED", f"{action} {status}: {detail}"


def _wait_alive(store_name):
    deadline = time.monotonic() + HEARTBEAT_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _agent_alive(store_name):
            return True
        time.sleep(10)
    return False


def _online_device(store_name):
    """(device, agent snapshot, why-not). The first online controller of the
    store that has the Store Agent installed."""
    try:
        devices = store_devices(store_name)
    except Exception as exc:  # platform DB / controller tables unreachable
        logger.debug("[MORNING_REPAIR] device lookup failed for %s", store_name, exc_info=True)
        return None, None, f"device lookup failed ({exc}) -- PC offline?"
    if not devices:
        return None, None, "no Device Controller is enrolled for this store on this HO"
    for device, agent in devices:
        if device.get("online") and agent:
            return device, agent, None
    if any(d.get("online") for d, _ in devices):
        return None, None, "the store PC's controller has no Store Agent installed"
    return None, None, "the store PC's Device Controller is offline"


def prepare(store_name, progress=None):
    """Once a day before the first sync: update an outdated Store Agent.
    Returns a short note for the day log, or None when nothing was done.
    Not marked prepared while the store PC is offline, so it is tried again
    as soon as the PC comes up."""
    state = _day_state(store_name)
    if state["prepared"]:
        return None
    device, agent, why = _online_device(store_name)
    if not device:
        if why and "offline" not in why:
            state["prepared"] = True  # nothing this HO can do today
        return None
    state["prepared"] = True
    try:
        target = target_agent_version()
    except Exception as exc:
        return f"Agent update check failed: {exc}"
    current = agent.get("version")
    if not target or (current and _vkey(current) >= _vkey(target)):
        return None
    if progress:
        progress(f"Updating {store_name}'s Store Agent {current or '?'} -> {target}…")
    ok, text = _run(device, "update", target)
    logger.info("[MORNING_REPAIR] %s agent update %s -> %s: %s", store_name, current, target, text)
    if ok and agent.get("status") != "running":
        _run(device, "start")
    alive = _wait_alive(store_name) if ok else False
    if ok:
        state["steps"] += ["update", "reinstall"]  # one package install a day
        return f"Store Agent updated {current or '?'} -> {target}" + ("" if alive else " (no heartbeat yet)") + "."
    return f"Store Agent update to {target} failed ({text})."


def repair(store_name, reason, progress=None):
    """One repair step for a store whose sync failed or whose agent is not
    beating. Returns (did_something_that_worked, note); note None = no step
    left for today (or nothing this HO can reach)."""
    state = _day_state(store_name)
    device, agent, why = _online_device(store_name)
    if not device:
        return False, None if "offline" in (why or "") else f"Auto-repair unavailable: {why}."
    try:
        alive = _agent_alive(store_name)
    except Exception:
        alive = False
    try:
        target = target_agent_version()
    except Exception:
        target = None
    current = agent.get("version")
    outdated = bool(target and (not current or _vkey(current) < _vkey(target)))
    if alive:
        ladder = ["restart", "reinstall"]
    else:
        ladder = ["update", "reinstall"] if outdated else ["restart", "reinstall"]
    step = next((s for s in ladder if s not in state["steps"]), None)
    if step is None:
        return False, None
    state["steps"] += ["update", "reinstall"] if step in ("update", "reinstall") else [step]
    if step in ("update", "reinstall"):
        if not target:
            return False, "Auto-repair: no Store Agent package in this HO's catalog to install."
        if progress:
            progress(f"Auto-repair: installing Store Agent {target} on {store_name} ({reason})…")
        ok, text = _run(device, "update", target)
        if ok:
            _run(device, "start")
        label = f"Store Agent {'updated ' + (current or '?') + ' -> ' if step == 'update' else 'reinstalled '}{target}"
    else:
        if progress:
            progress(f"Auto-repair: restarting {store_name}'s Store Agent ({reason})…")
        ok, text = _run(device, "restart")
        label = "Store Agent restarted"
    logger.info("[MORNING_REPAIR] %s %s (%s): %s", store_name, step, reason, text)
    if not ok:
        return False, f"Auto-repair {step} failed ({text})."
    alive = _wait_alive(store_name)
    return alive, f"Auto-repair: {label}" + (", heartbeat back." if alive else ", still no heartbeat.")


def steps_today(store_name):
    return list(_day_state(store_name)["steps"])


def prepared_today(store_name):
    return bool(_day_state(store_name)["prepared"])
