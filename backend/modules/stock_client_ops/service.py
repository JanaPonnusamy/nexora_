"""Business logic for Stock Client fleet management.

Admin side enforces the release lifecycle + the release!=rollout authorization
split; agent side binds an installation to the calling device's store and serves
the signed update manifest. Connectivity (ONLINE/STALE/OFFLINE) and version
status are DERIVED here from heartbeat recency, never stored stale.
"""
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from modules.stock_client_ops import repository as repo
from services.store_service import StoreService

# Where published packages live on the HO box (one subfolder per version),
# mirroring modules/agent_ops' agent_releases layout.
RELEASES_DIR = Path(__file__).resolve().parent.parent.parent / "stock_client_releases"

# Heartbeat-recency thresholds (configurable constants, spec section 11). A
# single missed 60s heartbeat must not flip a store OFFLINE.
_ONLINE_SECONDS = 120
_OFFLINE_SECONDS = 300


# ---- releases -------------------------------------------------------------

def list_releases():
    return {"releases": repo.list_releases()}


def approve_release(release_pk, actor=None):
    release = repo.get_release(release_pk)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    if release["status"] not in ("DRAFT", "TESTING"):
        raise HTTPException(status_code=409, detail=f"Release is {release['status']}, cannot approve")
    repo.set_release_status(release_pk, "APPROVED", actor=actor)
    return repo.get_release(release_pk)


def retire_release(release_pk, actor=None):
    release = repo.get_release(release_pk)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    repo.set_release_status(release_pk, "RETIRED", actor=actor)
    return repo.get_release(release_pk)


# ---- deployments (rollouts) ----------------------------------------------

def create_deployment(payload, actor=None):
    release = repo.get_release(payload.release_id)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    if release["status"] not in ("APPROVED", "ROLLED_OUT"):
        raise HTTPException(status_code=409,
                            detail="Release must be APPROVED before it can be deployed")

    if payload.scope == "ALL":
        store_ids = _active_store_ids()
    else:
        store_ids = [s for s in (payload.store_ids or []) if s]
        if not store_ids:
            raise HTTPException(status_code=400, detail="Select at least one store")
    # de-dup while preserving order
    store_ids = list(dict.fromkeys(store_ids))
    if not store_ids:
        raise HTTPException(status_code=400, detail="No target stores resolved")

    return repo.create_deployment(
        release_pk=payload.release_id, scope=payload.scope,
        store_ids=store_ids, created_by=actor,
    )


def authorize_deployment(deployment_id, actor=None):
    result = repo.authorize_deployment(deployment_id, actor=actor)
    if result == 0:
        raise HTTPException(status_code=404, detail="Deployment not found")
    if result == -1:
        raise HTTPException(status_code=409, detail="Deployment is not in DRAFT state")
    return repo.get_deployment(deployment_id)


def cancel_deployment(deployment_id, actor=None):
    updated = repo.cancel_deployment(deployment_id, actor=actor)
    if not updated:
        raise HTTPException(status_code=409, detail="Deployment cannot be cancelled")
    return repo.get_deployment(deployment_id)


def retry_target(deployment_id, target_id, actor=None):
    updated = repo.retry_target(deployment_id, target_id, actor=actor)
    if not updated:
        raise HTTPException(status_code=404, detail="Target not found")
    return repo.get_deployment(deployment_id)


def list_deployments():
    return {"deployments": repo.list_deployments()}


def get_deployment(deployment_id):
    deployment = repo.get_deployment(deployment_id)
    if not deployment:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return deployment


def _active_store_ids():
    rows = StoreService().get_all()
    # get_all() returns tuples: 0=store_id,1=tenant_id,2=store_code,3=store_name,
    # 4=server,5=database,6=is_active (see repositories/store_repository.py).
    return [str(r[0]) for r in rows if len(r) > 6 and r[6]]


# ---- monitoring -----------------------------------------------------------

def list_installations():
    rows = repo.list_installations()
    for row in rows:
        _decorate_connectivity(row)
    return {"installations": rows}


def get_installation(installation_id):
    installation = repo.get_installation(installation_id)
    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")
    _decorate_connectivity(installation)
    return installation


def _decorate_connectivity(row):
    """Add derived display fields. Never report the GUI as STOPPED when the
    watchdog itself isn't reporting - that's UNKNOWN (spec section 12)."""
    connectivity = _connectivity(row.get("last_heartbeat_at"))
    row["connectivity"] = connectivity
    online = connectivity == "ONLINE"
    row["watchdog"] = "ONLINE" if online else "OFFLINE"
    row["client"] = (row.get("client_status") or "UNKNOWN") if online else "UNKNOWN"
    current = row.get("client_version")
    target = row.get("target_version")
    if not online:
        row["version_status"] = "OFFLINE"
    elif target and target != current:
        row["version_status"] = "UPDATE AVAILABLE"
    else:
        row["version_status"] = "UP TO DATE"
    return row


def _connectivity(last_heartbeat):
    if not last_heartbeat:
        return "OFFLINE"
    try:
        age = (datetime.utcnow() - last_heartbeat).total_seconds()
    except TypeError:
        return "OFFLINE"
    if age < _ONLINE_SECONDS:
        return "ONLINE"
    if age < _OFFLINE_SECONDS:
        return "STALE"
    return "OFFLINE"


# ---- agent (device-token) -------------------------------------------------

def register_installation(payload, device, observed_ip=None):
    store_id, tenant_id = _device_scope(device)
    return repo.register_installation(
        installation_id=payload.installation_id,
        device_id=device.get("device_id"),
        tenant_id=tenant_id,
        store_id=store_id,
        fingerprint_hash=payload.fingerprint_hash,
        hostname=payload.hostname,
        os_version=payload.os_version,
        client_version=payload.client_version,
    )


def get_state(installation_id):
    return repo.get_installation_state(installation_id)


def record_heartbeat(payload, observed_ip=None):
    repo.record_heartbeat(
        installation_id=payload.installation_id,
        observed_ip=observed_ip,
        watchdog_version=payload.watchdog_version,
        watchdog_status=payload.watchdog_status,
        client_status=payload.client_status,
        client_version=payload.client_version,
        local_ip=payload.local_ip,
        os_version=payload.os_version,
        last_update_status=payload.last_update_status,
        last_error=payload.last_error,
        target_version=payload.target_version,
        target_status=payload.target_status,
        target_progress=payload.target_progress,
        target_error=payload.target_error,
    )
    return {"installation_id": payload.installation_id, "status": "ok"}


def download_path(version):
    release = repo.get_release_by_version(version)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    path = RELEASES_DIR / version / release["file_name"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Release file missing on server")
    return path, release["file_name"]


def _device_scope(device):
    """The store/tenant a device is bound to. Stock Client installs are one
    store per machine, so the first assigned store is authoritative."""
    store_ids = device.get("store_ids") or []
    tenant_ids = device.get("tenant_ids") or []
    store_id = store_ids[0] if store_ids else None
    tenant_id = tenant_ids[0] if tenant_ids else None
    return store_id, tenant_id
