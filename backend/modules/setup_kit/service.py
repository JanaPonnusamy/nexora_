"""Nexora Setup (one kit for every install type), HO side.

The kit on the PC: reads the system spec -> signs in -> picks the store ->
downloads + installs the Device Controller -> registers it (and the Store
Agent's identity) via /api/auth/device/register -> asks HO to install the
chosen apps. HO turns that into ordinary signed controller ``install``
commands, so the controller is the only thing that ever installs or updates
an app -- the same path HO uses for remote updates afterwards.
"""
from __future__ import annotations

import re

from fastapi import HTTPException

from config.database import get_connection
from dependencies.store_scope import is_super_admin
from modules.device_controller import packages, protocol, repository as dc_repo
from modules.device_controller import service as dc_service
from modules.device_identity import repository as device_repo

# What the kit can offer, in install order. The controller is mandatory: it is
# the installer, updater and watchdog for everything else on the PC.
COMPONENTS = [
    {"app_key": "controller", "label": "Device Controller", "required": True},
    {"app_key": "store_agent", "label": "Store Agent", "required": False},
    {"app_key": "stock_client", "label": "Stock Client", "required": False},
    {"app_key": "ho_backend", "label": "HO Backend", "required": False},
]
INSTALLABLE = {"store_agent", "stock_client"}   # via controller `install`
MIN_RAM_MB = 2048


def _version_key(version):
    return [int(p) if p.isdigit() else p for p in re.split(r"[.\-]", str(version))]


def latest_versions():
    """{app_key: newest package row} from this node's catalog (+ peers)."""
    packages.sync_local_packages()
    best = {}
    for row in dc_repo.list_packages():
        cur = best.get(row["app_key"])
        try:
            newer = cur is None or _version_key(row["version"]) > _version_key(cur["version"])
        except TypeError:  # mixed text/number parts: fall back to newest registration
            newer = cur is None
        if newer:
            best[row["app_key"]] = row
    return best


# ---- stores ----------------------------------------------------------------

def bindable_stores(user):
    """Super admin: every active store (picked at install time). Anyone else:
    only their own store, which the kit then binds without asking."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        sql = ("SELECT CAST(s.store_id AS varchar(36)), s.store_code, s.store_name, "
               "CAST(s.tenant_id AS varchar(36)), t.tenant_code, t.tenant_name "
               "FROM dbo.stores s LEFT JOIN dbo.tenants t ON t.tenant_id = s.tenant_id "
               "WHERE s.is_active = 1")
        params = []
        if not is_super_admin(user):
            if not user.get("store_id"):
                return {"choose": False, "stores": []}
            sql += " AND s.store_id = ?"
            params.append(str(user["store_id"]))
        cur.execute(sql + " ORDER BY t.tenant_code, s.store_code", *params)
        stores = [{"store_id": r[0].lower(), "store_code": r[1], "store_name": r[2],
                   "tenant_id": (r[3] or "").lower() or None, "tenant_code": r[4],
                   "tenant_name": r[5]} for r in cur.fetchall()]
    finally:
        conn.close()
    return {"choose": is_super_admin(user), "stores": stores}


# ---- plan ------------------------------------------------------------------

def plan(spec, user):
    """Which components this PC may get, with the package version for each."""
    spec = spec or {}
    latest = latest_versions()
    is64 = str(spec.get("arch") or "").lower() in ("amd64", "x64", "x86_64", "arm64")
    odbc = [d for d in (spec.get("odbc_drivers") or []) if "sql server" in str(d).lower()]
    ram = int(spec.get("ram_mb") or 0)
    warnings = []
    if ram and ram < MIN_RAM_MB:
        warnings.append(f"Only {ram} MB RAM: Nexora apps may run slowly on this PC.")
    out = []
    for comp in COMPONENTS:
        key = comp["app_key"]
        pkg = latest.get(key)
        eligible, reason = True, None
        if key == "ho_backend":
            eligible, reason = False, "HO installs use the HO path (coming next)."
        elif key == "stock_client" and not is64:
            eligible, reason = False, "The Stock Client needs 64-bit Windows."
        elif key == "store_agent" and not odbc:
            reason = "No SQL Server ODBC driver found: install ODBC Driver 17 before the agent can sync."
        if eligible and not pkg:
            eligible, reason = False, "No package published on HO yet."
        if key == "ho_backend" and not is_super_admin(user):
            eligible, reason = False, "Only a super admin can install an HO."
        out.append({**comp, "eligible": eligible, "reason": reason,
                    "version": pkg["version"] if pkg else None,
                    "sha256": pkg["sha256"] if pkg else None,
                    "file_name": pkg["file_name"] if pkg else None,
                    "file_size": pkg["file_size"] if pkg else None})
    return {"components": out, "warnings": warnings}


def controller_package(version):
    """(path, file_name) of a controller release for the kit to download."""
    found = packages.ensure_local("controller", version)
    if not found:
        raise HTTPException(status_code=404, detail=f"Controller {version} is not available on this HO")
    return found


# ---- install ---------------------------------------------------------------

def _can_manage(device, user):
    if is_super_admin(user):
        return True
    owner = str(device.get("registered_by_user_id") or "").lower()
    return bool(owner) and owner == str(user.get("sub") or "").lower()


def queue_install(controller_device_id, components, install_dirs, user):
    device = device_repo.get_device(controller_device_id)
    if not device or device.get("status") != "active":
        raise HTTPException(status_code=404, detail="This PC's Device Controller is not registered")
    if not _can_manage(device, user):
        raise HTTPException(status_code=403, detail="This PC was registered by another user")
    latest = latest_versions()
    actor = user.get("username") or user.get("sub")
    queued = []
    for key in components or []:
        if key not in INSTALLABLE:
            continue
        if key not in protocol.APP_ACTIONS or "install" not in protocol.APP_ACTIONS[key]:
            continue
        pkg = latest.get(key)
        if not pkg:
            raise HTTPException(status_code=409, detail=f"No {key} package published on HO")
        args = {"version": pkg["version"]}
        if (install_dirs or {}).get(key):
            args["install_dir"] = install_dirs[key]
        cmd = dc_service.create_command(controller_device_id, key, "install", args, actor)
        queued.append({"app_key": key, "version": pkg["version"], "command_id": cmd["command_id"]})
    return {"commands": queued}


def command_status(ids, user):
    out = []
    for cid in ids:
        cmd = dc_repo.get_command(cid)
        if not cmd:
            continue
        if not is_super_admin(user) and cmd.get("requested_by") != (user.get("username") or user.get("sub")):
            continue
        out.append({k: cmd.get(k) for k in ("command_id", "app_key", "action", "status",
                                             "result_text", "finished_at")})
    return {"commands": out}
