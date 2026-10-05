from datetime import datetime, timezone

from fastapi import HTTPException

from modules.licensing import repository
from modules.licensing.db_resolver import encrypt_license_db_password

DEFAULT_TRIAL_DAYS = 14
_VALID_MODES = {"SHARED", "DEDICATED"}


def start_trial(tenant_id, trial_days=DEFAULT_TRIAL_DAYS):
    repository.start_trial(tenant_id, trial_days)


def checkin(store_id, agent_version=None):
    tenant_id = repository.resolve_tenant_id_for_store(store_id)
    if not tenant_id:
        raise HTTPException(status_code=404, detail="Store not found")

    repository.expire_trial_if_due(tenant_id)
    repository.record_checkin(store_id, tenant_id, agent_version)

    row = repository.get_license_row(tenant_id)
    if not row:
        # Pre-existing tenant with no license row yet (shouldn't happen after
        # the 0001 migration backfill, but fail open rather than lock a store
        # out over a data gap).
        return {"license_state": "licensed", "days_remaining": None,
                "trial_ends_at": None, "message": None}

    days_remaining = None
    message = None
    if row["license_state"] in ("trial_active", "trial_expired"):
        ends = row["trial_ends_at"]
        if ends:
            delta = ends.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
            days_remaining = max(0, delta.days)
    if row["license_state"] == "trial_expired":
        message = "Trial expired. Contact Nexora to activate your license."
    elif row["license_state"] == "revoked":
        message = "License revoked. Contact Nexora to reactivate."

    return {
        "license_state": row["license_state"],
        "days_remaining": days_remaining,
        "trial_ends_at": row["trial_ends_at"],
        "message": message,
    }


def list_tenants(tenant_id_filter=None):
    return repository.list_tenants_with_status(tenant_id_filter)


def get_tenant_license(tenant_id):
    row = repository.get_license_row(tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="Tenant has no license record")
    row["audit"] = repository.get_audit_log(tenant_id)
    return row


def issue_key(tenant_id, license_key, issued_by, expires_at=None, notes=None):
    try:
        repository.issue_key(tenant_id, license_key, issued_by, expires_at, notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return repository.get_license_row(tenant_id)


def revoke(tenant_id, revoked_by, notes=None):
    try:
        repository.revoke(tenant_id, revoked_by, notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return repository.get_license_row(tenant_id)


def renew(tenant_id, expires_at, issued_by):
    try:
        repository.renew(tenant_id, expires_at, issued_by)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return repository.get_license_row(tenant_id)


def set_db_mode(tenant_id, mode, server=None, database=None, username=None,
                 password=None, driver=None):
    mode = (mode or "").upper()
    if mode not in _VALID_MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(_VALID_MODES)}")
    if mode == "DEDICATED" and not (server and database and username and password):
        raise HTTPException(
            status_code=400,
            detail="server, database, username and password are required for DEDICATED mode",
        )
    encrypted = encrypt_license_db_password(password) if mode == "DEDICATED" else None
    try:
        repository.set_db_mode(
            tenant_id, mode,
            server=server if mode == "DEDICATED" else None,
            database=database if mode == "DEDICATED" else None,
            username=username if mode == "DEDICATED" else None,
            password_encrypted=encrypted,
            driver=driver if mode == "DEDICATED" else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"tenant_id": tenant_id, "license_db_mode": mode}
