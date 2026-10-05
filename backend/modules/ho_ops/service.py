"""HO self-update logic — supports two kinds of HO node.

* GIT nodes (the build box, NODE9-PC): a source checkout. `start_self_update()`
  runs deploy_ho_prod.bat (git pull + reinstall + restart) detached.
* EXE nodes (.32, .73): installed from HO_Setup.exe, running the frozen
  `HO_Backend.exe` as the UniNexHO Windows service, with no git. They PULL a
  signed bundle (published by ho_setup/publish_ho_release.py on the build node)
  and hot-swap it behind the service via a detached updater.

Both detach the actual work so a node can restart itself from within the request
it is still answering. The orchestrator helpers fan out to peers over HTTP,
forwarding the caller's bearer so each peer enforces super-admin itself.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
DEPLOY_SCRIPT = REPO_ROOT / "deploy_ho_prod.bat"
RELEASES_DIR = BACKEND_DIR / "ho_backend_releases"
PUBLIC_KEY = BACKEND_DIR / "config" / "stock_release_signing_key.pub.pem"
_GIT_TIMEOUT = 20

# Frozen-exe node identity (ho_setup.SERVICE_NAME / BACKEND_EXE_NAME). Hardcoded
# so ho_ops never has to import ho_setup (absent inside the exe bundle).
HO_SERVICE_NAME = "UniNexHO"
HO_EXE_NAME = "HO_Backend.exe"
VERSION_MARKER = "HO_BACKEND_VERSION.txt"


# ---- node-kind detection --------------------------------------------------

def _frozen_install_dir():
    """Install dir when running as the frozen HO_Backend.exe, else None."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


def _exe_version(install_dir: Path):
    try:
        marker = install_dir / VERSION_MARKER
        if marker.is_file():
            return marker.read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    return None


def _git(*args, timeout=_GIT_TIMEOUT):
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
    try:
        from api.app import app

        return len([r for r in app.routes
                    if "stock-client" in getattr(r, "path", "")])
    except Exception:
        return 0


def local_status() -> dict:
    install_dir = _frozen_install_dir()
    is_exe = install_dir is not None
    is_git = (REPO_ROOT / ".git").exists() and not is_exe

    status = {
        "hostname": socket.gethostname(),
        "platform": f"{platform.system()} {platform.release()}",
        "kind": "exe" if is_exe else ("git" if is_git else "unknown"),
        "fleet_routes": _fleet_routes_live(),
    }

    if is_exe:
        status.update({
            "is_git": False,
            "install_dir": str(install_dir),
            "service_name": HO_SERVICE_NAME,
            "exe_version": _exe_version(install_dir),
            # Whether this build can self-apply a pulled bundle. The actual
            # "is there a newer version" decision is made by the orchestrator,
            # which knows the published latest.
            "can_self_update": sys.platform == "win32",
            # behind/up_to_date are filled by the orchestrator for exe nodes.
            "behind_main": None,
            "up_to_date": None,
        })
        return status

    # --- git node ---
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") if is_git else None
    head = _git("rev-parse", "--short", "HEAD") if is_git else None
    subject = _git("log", "-1", "--pretty=%s") if is_git else None
    committed = _git("log", "-1", "--pretty=%cI") if is_git else None
    behind = None
    if is_git:
        _git("fetch", "origin", "main", timeout=25)
        count = _git("rev-list", "--count", "HEAD..origin/main")
        try:
            behind = int(count) if count is not None else None
        except ValueError:
            behind = None
    status.update({
        "is_git": is_git,
        "branch": branch,
        "head": head,
        "subject": subject,
        "committed_at": committed,
        "behind_main": behind,
        "up_to_date": (behind == 0) if behind is not None else None,
        "dirty": bool(_git("status", "--porcelain")) if is_git else False,
        "can_self_update": bool(is_git and sys.platform == "win32" and DEPLOY_SCRIPT.is_file()),
        "deploy_script": str(DEPLOY_SCRIPT) if DEPLOY_SCRIPT.is_file() else None,
    })
    return status


# ---- published HO backend release (for exe nodes) -------------------------

def latest_backend_release() -> dict | None:
    """The newest bundle this (build) node has published, or None."""
    try:
        manifest = RELEASES_DIR / "latest.json"
        if manifest.is_file():
            return json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return None


def backend_release_path(version: str):
    from fastapi import HTTPException

    manifest = RELEASES_DIR / version / "manifest.json"
    if not manifest.is_file():
        raise HTTPException(status_code=404, detail="Release not found")
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    path = RELEASES_DIR / version / meta["file_name"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Release file missing on server")
    return path, meta["file_name"]


# ---- self-update ----------------------------------------------------------

def start_self_update(source_url: str | None = None, auth_header: str | None = None) -> dict:
    """Dispatch to the git or exe update path based on this node's kind."""
    status = local_status()
    if status["kind"] == "exe":
        return _start_exe_update(status, source_url, auth_header)
    return _start_git_update(status)


def _start_git_update(status) -> dict:
    if not status.get("can_self_update"):
        reason = ("not a git checkout" if not status.get("is_git")
                  else "self-update is only supported on Windows HO nodes"
                  if sys.platform != "win32"
                  else f"deploy script missing ({DEPLOY_SCRIPT})")
        return {"started": False, "reason": reason, **status}

    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            ["cmd", "/c", str(DEPLOY_SCRIPT)], cwd=str(REPO_ROOT),
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True,
        )
    except OSError as ex:
        return {"started": False, "reason": f"could not launch updater: {ex}", **status}
    return {"started": True, "kind": "git", "hostname": status["hostname"],
            "from_head": status.get("head"),
            "message": "Update started; backend will restart shortly."}


def _start_exe_update(status, source_url, auth_header) -> dict:
    """Pull the latest published bundle from the build node, verify it, and spawn
    a detached updater that stops UniNexHO, swaps the files, restarts, and rolls
    back on failure."""
    import requests

    if sys.platform != "win32":
        return {"started": False, "reason": "exe self-update is Windows-only", **status}
    install_dir = Path(status["install_dir"])

    # Resolve the release: from the orchestrator node (source_url) or locally.
    headers = {"Authorization": auth_header} if auth_header else {}
    try:
        if source_url:
            base = source_url.rstrip("/")
            meta = requests.get(f"{base}/api/ho-ops/backend-release/latest",
                                headers=headers, timeout=15).json()
        else:
            meta = latest_backend_release()
    except Exception as ex:
        return {"started": False, "reason": f"could not read latest release: {ex}", **status}
    if not meta or not meta.get("version"):
        return {"started": False, "reason": "no HO backend release has been published yet", **status}

    version = meta["version"]
    if status.get("exe_version") == version:
        return {"started": False, "reason": f"already on {version}", **status}

    staging = Path(tempfile.gettempdir()) / "nexora-ho-update"
    staging.mkdir(parents=True, exist_ok=True)
    zip_path = staging / meta["file_name"]

    # Download the bundle.
    try:
        dl = (f"{source_url.rstrip('/')}/api/ho-ops/backend-release/download/{version}"
              if source_url else None)
        if dl:
            with requests.get(dl, headers=headers, stream=True, timeout=600) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        f.write(chunk)
        else:
            # self is the build node: copy the local file.
            src, _ = backend_release_path(version)
            import shutil
            shutil.copy2(src, zip_path)
    except Exception as ex:
        return {"started": False, "reason": f"download failed: {ex}", **status}

    # Verify sha256 + Ed25519 signature before anything is swapped.
    try:
        _verify_bundle(zip_path, meta)
    except Exception as ex:
        zip_path.unlink(missing_ok=True)
        return {"started": False, "reason": f"verification failed: {ex}", **status}

    # Write + spawn the detached updater.
    updater = staging / "ho_exe_update.bat"
    backup = staging / "backup"
    updater.write_text(_UPDATER_BAT, encoding="utf-8")
    flags = 0
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(
            ["cmd", "/c", str(updater), str(zip_path), str(install_dir),
             HO_SERVICE_NAME, str(backup)],
            cwd=str(staging), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=flags, close_fds=True,
        )
    except OSError as ex:
        return {"started": False, "reason": f"could not launch updater: {ex}", **status}

    return {"started": True, "kind": "exe", "hostname": status["hostname"],
            "from_version": status.get("exe_version"), "to_version": version,
            "message": f"Updating to {version}; UniNexHO will restart shortly."}


def _verify_bundle(path: Path, meta: dict):
    from modules.device_identity import crypto

    actual = _sha256_of(path)
    expected = (meta.get("sha256") or "").strip().lower()
    if actual.lower() != expected:
        raise RuntimeError(f"sha256 mismatch: expected {expected}, got {actual}")
    pub = _public_key()
    if not pub:
        raise RuntimeError("no release-signing public key available")
    manifest = f"{meta['version']}|{actual}|{os.path.getsize(path)}".encode("utf-8")
    sig = base64.b64decode(meta.get("signature") or "")
    if not crypto.verify(pub, manifest, sig):
        raise RuntimeError("Ed25519 signature verification failed")


def _public_key():
    for cand in (PUBLIC_KEY, _bundled("stock_release_signing_key.pub.pem")):
        try:
            if cand and cand.is_file():
                return cand.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _bundled(name):
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) / name) if base else None


def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Detached updater: stop the service, back up the current install (code only, not
# config/logs/uploads/backups), expand the new bundle over it, restart, health
# check, and roll back if it does not come up. Args:
#   %1 zip  %2 install_dir  %3 service  %4 backup_dir
_UPDATER_BAT = r"""@echo off
setlocal enabledelayedexpansion
set ZIP=%~1
set INSTALL=%~2
set SVC=%~3
set BACKUP=%~4
REM Let the HTTP response flush and the request finish before we stop ourselves.
timeout /t 3 /nobreak >nul

sc stop "%SVC%" >nul 2>&1
REM Wait for STOPPED (up to ~30s).
for /l %%i in (1,1,15) do (
    sc query "%SVC%" | findstr /i "STOPPED" >nul && goto stopped
    timeout /t 2 /nobreak >nul
)
:stopped

REM Back up the current code (exclude runtime/config dirs).
if exist "%BACKUP%" rmdir /s /q "%BACKUP%"
mkdir "%BACKUP%"
robocopy "%INSTALL%" "%BACKUP%" /E /XD logs uploads backups config >nul

REM Apply the new bundle over the install (config/logs/etc. untouched).
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force -LiteralPath '%ZIP%' -DestinationPath '%INSTALL%'"

sc start "%SVC%" >nul 2>&1

REM Health check: wait up to ~90s for :8000 to answer.
set OK=0
for /l %%i in (1,1,45) do (
    if "!OK!"=="0" (
        for /f %%c in ('curl -s -o nul -w "%%{http_code}" --max-time 3 http://127.0.0.1:8000/health') do set CODE=%%c
        if "!CODE!"=="200" (set OK=1) else (timeout /t 2 /nobreak >nul)
    )
)
if "!OK!"=="1" goto done

REM Rollback: restore the backup and restart.
sc stop "%SVC%" >nul 2>&1
timeout /t 5 /nobreak >nul
robocopy "%BACKUP%" "%INSTALL%" /E >nul
sc start "%SVC%" >nul 2>&1

:done
endlocal
"""


# ---- orchestration over peer HO nodes -------------------------------------

def _peer_urls() -> list[dict]:
    """The OTHER HO backend boxes to orchestrate.

    Primary source: the NEXORA_HO_NODES env var — a comma-separated list of each
    peer box's base URL (e.g. "http://192.168.10.32:8000,http://192.168.10.73:8000").
    This is deliberately NOT the bootstrap ho_routes registry: ho_routes holds the
    failover URLs store agents use to reach the ONE public HO (all pointing at the
    same box), not the list of distinct HO backend machines. List only the OTHER
    boxes here — the node serving the page is already added as "This node".
    Falls back to ho_routes only when the env var is unset (legacy behaviour)."""
    env = os.getenv("NEXORA_HO_NODES", "").strip()
    if env:
        out = []
        for item in env.split(","):
            u = item.strip().rstrip("/")
            if u:
                out.append({"url": u, "label": None})
        return out
    try:
        from modules.bootstrap import repository as boot_repo

        return boot_repo.get_active_routes() or []
    except Exception:
        return []


def _decorate_exe_update(node: dict, latest: dict | None):
    """For an exe node, derive update-available from the published latest."""
    if node.get("kind") != "exe":
        return
    if not latest:
        node["latest_release"] = None
        node["up_to_date"] = None
        return
    node["latest_release"] = latest.get("version")
    cur = node.get("exe_version")
    node["up_to_date"] = (cur == latest.get("version")) if cur else None


def list_nodes(auth_header: str | None) -> dict:
    import requests

    latest = latest_backend_release()
    self_status = local_status()
    self_status.update({"is_self": True, "url": None, "label": "This node",
                        "reachable": True})
    _decorate_exe_update(self_status, latest)
    nodes = [self_status]

    headers = {"Authorization": auth_header} if auth_header else {}
    for route in _peer_urls():
        url = (route.get("url") or "").rstrip("/")
        if not url:
            continue
        entry = {"url": url, "label": route.get("label"), "is_self": False}
        try:
            resp = requests.get(f"{url}/api/ho-ops/status", headers=headers, timeout=12)
            resp.raise_for_status()
            entry.update(resp.json())
            entry["reachable"] = True
            _decorate_exe_update(entry, latest)
        except Exception as ex:
            entry["reachable"] = False
            entry["error"] = str(ex)
        entry["is_self"] = False
        entry["url"] = url
        nodes.append(entry)

    return {"nodes": nodes, "latest_release": latest.get("version") if latest else None}


def update_nodes(targets: list[dict], auth_header: str | None,
                 source_url: str | None = None) -> dict:
    import requests

    results = []
    headers = {"Authorization": auth_header} if auth_header else {}
    self_targets = [t for t in targets if t.get("is_self")]
    peer_targets = [t for t in targets if not t.get("is_self") and t.get("url")]

    for t in peer_targets:
        url = t["url"].rstrip("/")
        try:
            resp = requests.post(f"{url}/api/ho-ops/self-update",
                                 json={"source_url": source_url},
                                 headers=headers, timeout=20)
            resp.raise_for_status()
            results.append({"url": url, "ok": True, "result": resp.json()})
        except Exception as ex:
            results.append({"url": url, "ok": False, "error": str(ex)})

    for _ in self_targets:
        res = start_self_update(source_url=source_url, auth_header=auth_header)
        results.append({"url": None, "is_self": True,
                        "ok": bool(res.get("started")), "result": res})

    return {"results": results}
