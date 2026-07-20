"""Business logic for managed desktop clients."""

import re

from fastapi import HTTPException

from modules.desktop_client import repository as repo


def activate(payload):
    return repo.activate_request(payload)


def config(client_id, app_version=None):
    row = repo.get_config(client_id)
    if not row:
        return {"client_id": client_id, "status": "unknown", "force_update": False}
    if app_version and row.get("min_version") and _version_lt(app_version, row["min_version"]):
        row["force_update"] = True
    return row


def heartbeat(payload):
    row = repo.heartbeat(payload.client_id, payload.app_version)
    if not row:
        return {"client_id": payload.client_id, "status": "unknown"}
    return row


def list_devices():
    return {"devices": repo.list_devices()}


def approve(client_id, payload):
    row = repo.approve_device(client_id, payload)
    if not row:
        raise HTTPException(status_code=404, detail="Desktop client not found")
    return row


def _version_lt(current, minimum):
    def parts(value):
        out = []
        for part in str(value).split("."):
            match = re.match(r"\d+", part)
            out.append(int(match.group(0)) if match else 0)
        return out

    return parts(current) < parts(minimum)
