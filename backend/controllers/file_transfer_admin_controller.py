"""Read-only admin visibility into FILE_TRANSFER packages (objective 9:
auditable). Mirrors the existing admin-controller pattern (authenticated via
get_current_user, same as sync_admin_controller.py) -- not the unattended
agent-facing surface.

Mail config surface (Phase 2 extraction): HO's FILE_TRANSFER config is,
deliberately, plain environment variables read at process start (see
modules/sync/file_transfer_config.py's docstring -- "not a new settings
system"), never a database table. So unlike the Store Mail Transfer UI
(which writes agent_config.json), this is a VIEW + live connection test
against whatever NEXORA_FILE_TRANSFER_* / NEXORA_HO_MAIL_RECEIVER_* env vars
are already set on the machine -- there is no "Save" here, matching that
existing architecture decision rather than introducing a second config
store for the same values. Passwords are never returned, only the name of
the env var that holds them (same *_env convention used everywhere else in
FILE_TRANSFER).
"""
import imaplib
import os
import smtplib

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from config.database import get_connection
from dependencies.auth import get_current_user
from modules.sync import file_transfer_config as cfg
from modules.sync import file_transfer_scheduler as scheduler
from modules.sync import file_transfer_repository as repo

router = APIRouter(prefix="/api/sync/file-transfer", tags=["sync-file-transfer"])


@router.get("/status")
def get_status(user=Depends(get_current_user)):
    return {
        "enabled": cfg.enabled(),
        "transport_mode": cfg.transport_config().get("mode"),
        "tick_seconds": cfg.tick_seconds(),
        "receiver": scheduler.get_status() if hasattr(scheduler, "get_status") else None,
    }


@router.get("/packages")
def list_packages(status: str = None, limit: int = 100, user=Depends(get_current_user)):
    repo.ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        if status:
            cur.execute(
                """
                SELECT TOP (?) package_id, execution_id, tenant_id, store_id,
                       source_filename, checksum, transport_mode, status,
                       total_rows, total_chunks, total_tables, tables_imported,
                       tables_failed, received_at, import_started_at,
                       import_completed_at, error_message
                FROM sync.file_sync_packages
                WHERE status = ?
                ORDER BY received_at DESC
                """,
                (limit, status),
            )
        else:
            cur.execute(
                """
                SELECT TOP (?) package_id, execution_id, tenant_id, store_id,
                       source_filename, checksum, transport_mode, status,
                       total_rows, total_chunks, total_tables, tables_imported,
                       tables_failed, received_at, import_started_at,
                       import_completed_at, error_message
                FROM sync.file_sync_packages
                ORDER BY received_at DESC
                """,
                (limit,),
            )
        cols = [c[0] for c in cur.description]
        out = []
        for row in cur.fetchall():
            item = dict(zip(cols, row))
            for key in ("package_id", "execution_id", "tenant_id", "store_id"):
                if item.get(key) is not None:
                    item[key] = str(item[key])
            for key in ("received_at", "import_started_at", "import_completed_at"):
                if item.get(key) is not None:
                    item[key] = item[key].isoformat()
            out.append(item)
        return out
    finally:
        conn.close()


class _TestResult(BaseModel):
    ok: bool
    detail: str


def _email_cfg_or_error():
    if cfg.transport_config().get("mode") != "EMAIL":
        raise RuntimeError(
            "NEXORA_FILE_TRANSFER_MODE is not EMAIL -- no mailbox is configured"
        )
    return cfg.transport_config()["email"]


def _password(email_cfg):
    env_name = email_cfg.get("password_env")
    value = os.environ.get(env_name) if env_name else None
    if not value:
        raise RuntimeError(
            f"Environment variable '{env_name}' is not set on this HO server"
        )
    return value


@router.get("/mail-config")
def get_mail_config(user=Depends(get_current_user)):
    """View only -- see module docstring. Never returns the password itself,
    only the name of the env var that holds it."""
    transport = cfg.transport_config()
    email_cfg = transport.get("email") or {}
    return {
        "enabled": cfg.enabled(),
        "mode": transport.get("mode"),
        "smtp_host": email_cfg.get("smtp_host"),
        "smtp_port": email_cfg.get("smtp_port"),
        "imap_host": email_cfg.get("imap_host"),
        "imap_port": email_cfg.get("imap_port"),
        "imap_folder": email_cfg.get("imap_folder"),
        "username": email_cfg.get("username"),
        "password_env": email_cfg.get("password_env"),
        "password_env_set": bool(
            email_cfg.get("password_env") and os.environ.get(email_cfg["password_env"])
        ),
        "default_store_address": email_cfg.get("default_store_address"),
    }


@router.post("/mail-config/test-smtp", response_model=_TestResult)
def test_smtp(user=Depends(get_current_user)):
    """Actually connects -- never a fabricated success (objective 30)."""
    try:
        email_cfg = _email_cfg_or_error()
        password = _password(email_cfg)
        host = email_cfg.get("smtp_host")
        port = int(email_cfg.get("smtp_port", 587))
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(email_cfg.get("username"), password)
        return _TestResult(ok=True, detail=f"Connected and authenticated to {host}:{port}")
    except Exception as ex:
        return _TestResult(ok=False, detail=str(ex))


@router.post("/mail-config/test-imap", response_model=_TestResult)
def test_imap(user=Depends(get_current_user)):
    try:
        email_cfg = _email_cfg_or_error()
        password = _password(email_cfg)
        host = email_cfg.get("imap_host")
        port = int(email_cfg.get("imap_port", 993))
        folder = email_cfg.get("imap_folder", "INBOX")
        conn = imaplib.IMAP4_SSL(host, port)
        try:
            conn.login(email_cfg.get("username"), password)
            conn.select(folder)
        finally:
            conn.logout()
        return _TestResult(ok=True, detail=f"Connected and selected {folder} on {host}:{port}")
    except Exception as ex:
        return _TestResult(ok=False, detail=str(ex))
