"""HO self-update logic.

`local_status()` reads THIS node's git state live (never cached) and whether it
is behind origin/main. `start_self_update()` spawns the existing
`deploy_ho_prod.bat` in a DETACHED process so the update survives the backend
restarting itself (the same reason the store/stock watchdogs are separate
processes -- a server cannot cleanly restart itself from within a request it is
still answering). The orchestrator helpers fan out to peer HO nodes over HTTP,
forwarding the caller's bearer so each peer enforces super-admin itself.
"""
from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
DEPLOY_SCRIPT = REPO_ROOT / "deploy_ho_prod.bat"
_GIT_TIMEOUT = 20


def _git(*args, timeout=_GIT_TIMEOUT):
    """Run a git command in the repo root; return stripped stdout or None."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _fleet_routes_live() -> int:
    """How many stock-client-ops routes this process is actually serving -- the
    reliable 'is the new code running' signal (info.version is static)."""
    try:
        from api.app import app

        return len([r for r in app.routes
                    if "stock-client" in getattr(r, "path", "")])
    except Exception:
        return 0


def local_status() -> dict:
    is_git = (REPO_ROOT / ".git").exists()
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") if is_git else None
    head = _git("rev-parse", "--short", "HEAD") if is_git else None
    subject = _git("log", "-1", "--pretty=%s") if is_git else None
    committed = _git("log", "-1", "--pretty=%cI") if is_git else None

    # Best-effort freshness: fetch, then count how far behind origin/main we are.
    behind = None
    if is_git:
        _git("fetch", "origin", "main", timeout=25)
        count = _git("rev-list", "--count", "HEAD..origin/main")
        try:
            behind = int(count) if count is not None else None
        except ValueError:
            behind = None

    dirty = bool(_git("status", "--porcelain")) if is_git else False

    return {
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}",
        "is_git": is_git,
        "branch": branch,
        "head": head,
        "subject": subject,
        "committed_at": committed,
        "behind_main": behind,
        "up_to_date": (behind == 0) if behind is not None else None,
        "dirty": dirty,
        "fleet_routes": _fleet_routes_live(),
        "can_self_update": bool(
            is_git and sys.platform == "win32" and DEPLOY_SCRIPT.is_file()
        ),
        "deploy_script": str(DEPLOY_SCRIPT) if DEPLOY_SCRIPT.is_file() else None,
    }


def start_self_update() -> dict:
    """Spawn the deploy script detached so it outlives this backend's restart.

    The script pulls origin/main, reinstalls deps, kills :8000 (this process),
    and relaunches via the NexoraBackend scheduled task. Because it is detached
    (new process group, no inherited handles), killing :8000 does not take the
    updater down with it. A short delay inside the script lets this HTTP response
    flush first."""
    status = local_status()
    if not status["can_self_update"]:
        reason = (
            "not a git checkout" if not status["is_git"]
            else "self-update is only supported on Windows HO nodes"
            if sys.platform != "win32"
            else f"deploy script missing ({DEPLOY_SCRIPT})"
        )
        return {"started": False, "reason": reason, **status}

    # `cmd /c start` returns immediately; the spawned window runs independently.
    # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP so the taskkill of :8000 inside
    # the script cannot cascade back to this updater.
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        subprocess.Popen(
            ["cmd", "/c", str(DEPLOY_SCRIPT)],
            cwd=str(REPO_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
    except OSError as ex:
        return {"started": False, "reason": f"could not launch updater: {ex}",
                **status}

    return {
        "started": True,
        "hostname": status["hostname"],
        "from_head": status["head"],
        "message": "Update started. The backend will restart shortly; re-check "
                   "status in ~30-60s.",
    }


# ---- orchestration over peer HO nodes -------------------------------------

def _peer_urls() -> list[dict]:
    """HO node base URLs from the bootstrap ho_routes registry (the same list
    store agents fail over across)."""
    try:
        from modules.bootstrap import repository as boot_repo

        return boot_repo.get_active_routes() or []
    except Exception:
        return []


def list_nodes(auth_header: str | None) -> dict:
    """This node's status plus each peer's, fetched server-side (no CORS)."""
    import requests

    self_status = local_status()
    self_status["is_self"] = True
    self_status["url"] = None
    self_status["label"] = "This node"
    self_status["reachable"] = True
    nodes = [self_status]

    headers = {"Authorization": auth_header} if auth_header else {}
    for route in _peer_urls():
        url = (route.get("url") or "").rstrip("/")
        if not url:
            continue
        entry = {"url": url, "label": route.get("label"), "is_self": False}
        try:
            resp = requests.get(f"{url}/api/ho-ops/status",
                                headers=headers, timeout=12)
            resp.raise_for_status()
            entry.update(resp.json())
            entry["reachable"] = True
        except Exception as ex:
            entry["reachable"] = False
            entry["error"] = str(ex)
        entry["is_self"] = False
        entry["url"] = url
        nodes.append(entry)

    return {"nodes": nodes}


def update_nodes(targets: list[dict], auth_header: str | None) -> dict:
    """Trigger self-update on each target. is_self targets are updated by direct
    call (last-ish), peers over HTTP with the caller's bearer forwarded."""
    import requests

    results = []
    headers = {"Authorization": auth_header} if auth_header else {}
    self_targets = [t for t in targets if t.get("is_self")]
    peer_targets = [t for t in targets if not t.get("is_self") and t.get("url")]

    # Peers first, so a (self) restart never cuts the loop short.
    for t in peer_targets:
        url = t["url"].rstrip("/")
        try:
            resp = requests.post(f"{url}/api/ho-ops/self-update",
                                 headers=headers, timeout=15)
            resp.raise_for_status()
            results.append({"url": url, "ok": True, "result": resp.json()})
        except Exception as ex:
            results.append({"url": url, "ok": False, "error": str(ex)})

    for _ in self_targets:
        res = start_self_update()
        results.append({"url": None, "is_self": True,
                        "ok": bool(res.get("started")), "result": res})

    return {"results": results}
