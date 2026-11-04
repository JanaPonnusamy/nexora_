"""Package catalog for controller-driven installs/updates.

Release files live only on the node that published them (normally the build
node). Each HO node scans its own release folders and registers what it holds
in dbo.dc_packages together with its own base URL, so every node (and the HO
UI on any node) sees the full catalog and every controller knows where to
download a given version from.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time
from pathlib import Path

from modules.device_controller import repository

BACKEND_DIR = Path(__file__).resolve().parents[2]

# app_key -> local release root (one sub-folder per version)
RELEASE_ROOTS = {
    "ho_backend": BACKEND_DIR / "ho_backend_releases",
    "stock_client": BACKEND_DIR / "stock_client_releases",
    "store_agent": BACKEND_DIR / "agent_releases",
    "controller": BACKEND_DIR / "device_controller_releases",
}

_SYNC_EVERY_SECONDS = 600
_sync_lock = threading.Lock()
_last_sync = 0.0


def self_base_url() -> str:
    """How other machines reach THIS node. NEXORA_SELF_URL wins; otherwise the
    primary LAN address + the port the service binds."""
    env = os.getenv("NEXORA_SELF_URL", "").strip().rstrip("/")
    if env:
        return env
    port = os.getenv("UNINEX_PORT") or os.getenv("PORT") or "8000"
    ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except OSError:
        pass
    return f"http://{ip}:{port}"


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_manifest(folder: Path):
    try:
        manifest = folder / "manifest.json"
        if manifest.is_file():
            return json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return None


def _first_file(folder: Path, suffixes):
    for item in sorted(folder.iterdir()):
        if item.is_file() and item.suffix.lower() in suffixes:
            return item
    return None


def _scan_app(app_key: str):
    """Yield {version, file_name, sha256, file_size, signature} for every
    release folder of app_key present on this node."""
    root = RELEASE_ROOTS[app_key]
    if not root.is_dir():
        return
    db_meta = repository.release_meta_from_legacy_tables(app_key)
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        version = folder.name
        manifest = _read_manifest(folder)
        if manifest and manifest.get("file_name"):
            path = folder / manifest["file_name"]
            if not path.is_file():
                continue
            yield {
                "version": manifest.get("version") or version,
                "file_name": manifest["file_name"],
                "sha256": manifest.get("sha256") or _sha256_of(path),
                "file_size": manifest.get("file_size") or path.stat().st_size,
                "signature": manifest.get("signature"),
            }
            continue
        path = _first_file(folder, {".exe", ".zip"})
        if path is None:
            continue
        meta = db_meta.get(version) or {}
        yield {
            "version": version,
            "file_name": path.name,
            "sha256": (meta.get("sha256") or _sha256_of(path)).strip().lower(),
            "file_size": meta.get("file_size") or path.stat().st_size,
            "signature": meta.get("signature"),
        }


def sync_local_packages(force: bool = False) -> int:
    """Register this node's release files in the shared catalog. Throttled;
    never raises (a scan problem must not break the endpoint calling it)."""
    global _last_sync
    if not force and time.time() - _last_sync < _SYNC_EVERY_SECONDS:
        return 0
    with _sync_lock:
        if not force and time.time() - _last_sync < _SYNC_EVERY_SECONDS:
            return 0
        _last_sync = time.time()
        count = 0
        base = self_base_url()
        for app_key in RELEASE_ROOTS:
            try:
                for pkg in _scan_app(app_key):
                    repository.upsert_package(app_key, pkg, base)
                    count += 1
            except Exception:
                continue
        try:
            count += sync_peer_catalogs()
        except Exception:
            pass
        return count


def local_package_path(app_key: str, version: str):
    """(path, file_name) of a release file held by THIS node, or None."""
    root = RELEASE_ROOTS.get(app_key)
    if root is None:
        return None
    folder = root / version
    if not folder.is_dir() or folder.resolve().parent != root.resolve():
        return None  # also blocks ../ traversal in `version`
    manifest = _read_manifest(folder)
    if manifest and manifest.get("file_name"):
        path = folder / manifest["file_name"]
        return (path, path.name) if path.is_file() else None
    path = _first_file(folder, {".exe", ".zip"})
    return (path, path.name) if path else None


# ---- peer mirror -----------------------------------------------------------
#
# Release files are published on the build node (.80, LAN only). An HO that
# serves internet stores (e.g. .32 via 122.252.246.181:8444) learns the peer's
# catalog and, the first time a device asks for a version it lacks, downloads
# it from the peer once (sha256-checked against the catalog) and keeps it, so
# controllers / Nexora Setup always download from their own HO.
#
#   NEXORA_PACKAGE_PEERS     comma-separated base URLs of nodes to mirror from
#   NEXORA_PACKAGE_PEER_KEY  shared secret; required on BOTH sides (unset = off)

PEER_KEY_HEADER = "X-Nexora-Peer-Key"
_fetch_lock = threading.Lock()


def peer_key() -> str:
    return os.getenv("NEXORA_PACKAGE_PEER_KEY", "").strip()


def peer_urls() -> list:
    own = self_base_url()
    return [u.strip().rstrip("/") for u in os.getenv("NEXORA_PACKAGE_PEERS", "").split(",")
            if u.strip() and u.strip().rstrip("/") != own]


def peer_key_ok(presented) -> bool:
    import hmac

    key = peer_key()
    return bool(key) and bool(presented) and hmac.compare_digest(str(presented), key)


def local_catalog() -> list:
    """Packages whose files THIS node holds (served to peers)."""
    out = []
    for app_key in RELEASE_ROOTS:
        try:
            out += [{"app_key": app_key, **pkg} for pkg in _scan_app(app_key)]
        except Exception:
            continue
    return out


def sync_peer_catalogs() -> int:
    """Register every peer's packages here (source = that peer), so this node's
    catalog offers them before any file has been copied."""
    import requests

    if not peer_key():
        return 0
    count = 0
    for base in peer_urls():
        try:
            r = requests.get(f"{base}/api/device-controller/peer/catalog",
                             headers={PEER_KEY_HEADER: peer_key()}, timeout=20)
            r.raise_for_status()
            for pkg in r.json().get("packages") or []:
                if pkg.get("app_key") in RELEASE_ROOTS and pkg.get("sha256"):
                    repository.upsert_package(pkg["app_key"], pkg, base)
                    count += 1
        except Exception:
            continue
    return count


def ensure_local(app_key: str, version: str):
    """local_package_path, fetching the file from a peer first if needed."""
    found = local_package_path(app_key, version)
    if found or not peer_key():
        return found
    pkg = repository.get_package(app_key, version)
    root = RELEASE_ROOTS.get(app_key)
    if not pkg or root is None:
        return None
    import requests

    with _fetch_lock:
        found = local_package_path(app_key, version)
        if found:
            return found
        folder = root / version
        if folder.resolve().parent != root.resolve():
            return None
        sources = [u for u in (pkg.get("source_urls") or "").split(",") if u]
        for base in [u.rstrip("/") for u in sources + peer_urls()]:
            if base == self_base_url():
                continue
            tmp = root / f".{app_key}-{version}.part"
            try:
                root.mkdir(parents=True, exist_ok=True)
                with requests.get(f"{base}/api/device-controller/peer/packages/{app_key}/{version}",
                                  headers={PEER_KEY_HEADER: peer_key()}, stream=True,
                                  timeout=(10, 600)) as r:
                    if r.status_code != 200:
                        continue
                    with open(tmp, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            f.write(chunk)
                if _sha256_of(tmp).lower() != str(pkg["sha256"]).strip().lower():
                    tmp.unlink()
                    continue
                folder.mkdir(parents=True, exist_ok=True)
                os.replace(str(tmp), str(folder / pkg["file_name"]))
                (folder / "manifest.json").write_text(json.dumps({
                    "version": version, "file_name": pkg["file_name"],
                    "sha256": str(pkg["sha256"]).strip().lower(),
                    "file_size": int(pkg["file_size"]), "signature": pkg.get("signature"),
                    "mirrored_from": base,
                }, indent=2), encoding="utf-8")
                repository.upsert_package(app_key, {
                    "version": version, "file_name": pkg["file_name"], "sha256": pkg["sha256"],
                    "file_size": pkg["file_size"], "signature": pkg.get("signature"),
                }, self_base_url())
                return local_package_path(app_key, version)
            except Exception:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                continue
    return None
