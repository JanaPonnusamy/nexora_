from pathlib import Path

from fastapi import HTTPException

from modules.agent_ops import repository

RELEASES_DIR = Path(__file__).resolve().parent.parent.parent / "agent_releases"

_VALID_STATES = {"RUNNING", "STOPPED"}


def get_watchdog_state(store_id):
    state = repository.get_watchdog_state(store_id)
    version = state["desired_version"]
    release = (
        repository.get_release(version) if version else repository.get_current_release()
    )
    return {
        "desired_state": state["desired_state"],
        "version": (
            {
                "version": release["version"],
                "sha256": release["sha256"],
                "file_size": release["file_size"],
                "download_url": f"/agent/watchdog/download/{release['version']}",
            }
            if release
            else None
        ),
    }


def record_heartbeat(payload):
    repository.record_watchdog_heartbeat(
        payload.store_id,
        payload.watchdog_version,
        payload.installed_agent_version,
        payload.service_state,
        payload.last_action,
    )
    return {"ok": True}


def download_path(version):
    release = repository.get_release(version)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
    path = RELEASES_DIR / release["version"] / release["file_name"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Release file missing on server")
    return path, release["file_name"]


def list_stores(tenant_id=None):
    return repository.list_agent_ops(tenant_id)


def list_releases():
    return repository.list_releases()


def list_logs(limit=100, store_id=None):
    return repository.list_agent_logs(limit=limit, store_id=store_id)


def set_state(store_id, desired_state):
    _validate_state(desired_state)
    updated = repository.set_desired_state([store_id], desired_state)
    if not updated:
        raise HTTPException(status_code=404, detail="Store agent not registered")
    return {"store_id": store_id, "desired_state": desired_state}


def set_state_bulk(store_ids, desired_state):
    _validate_state(desired_state)
    updated = repository.set_desired_state(store_ids, desired_state)
    return {"updated": updated, "desired_state": desired_state}


def set_version(store_id, desired_version):
    _validate_version(desired_version)
    updated = repository.set_desired_version([store_id], desired_version)
    if not updated:
        raise HTTPException(status_code=404, detail="Store agent not registered")
    return {"store_id": store_id, "desired_version": desired_version}


def set_version_bulk(store_ids, desired_version):
    _validate_version(desired_version)
    updated = repository.set_desired_version(store_ids, desired_version)
    return {"updated": updated, "desired_version": desired_version}


def _validate_state(desired_state):
    if desired_state not in _VALID_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"desired_state must be one of {sorted(_VALID_STATES)}",
        )


def _validate_version(desired_version):
    if desired_version is None:
        return
    release = repository.get_release(desired_version)
    if not release:
        raise HTTPException(status_code=404, detail="Release not found")
