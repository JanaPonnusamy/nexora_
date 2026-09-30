"""HO-side FILE_TRANSFER configuration -- plain environment variables, the
same convention already used across this backend (config/database.py,
api/app.py CORS, modules/sync/scheduler_service.py), not a new settings
system.

    NEXORA_FILE_TRANSFER_ENABLED=true
    NEXORA_FILE_TRANSFER_TICK_SECONDS=60
    NEXORA_FILE_TRANSFER_MODE=FILE_DROP|SFTP|EMAIL

    # FILE_DROP
    NEXORA_FILE_TRANSFER_ROOT=\\\\fileserver\\nexora_sync

    # SFTP
    NEXORA_FILE_TRANSFER_SFTP_HOST=...
    NEXORA_FILE_TRANSFER_SFTP_PORT=22
    NEXORA_FILE_TRANSFER_SFTP_USERNAME=...
    NEXORA_FILE_TRANSFER_SFTP_KEY_PATH=...
    NEXORA_FILE_TRANSFER_SFTP_PASSWORD_ENV=NEXORA_SFTP_PASSWORD   (name of the
        env var actually holding the secret -- never the secret itself)
    NEXORA_FILE_TRANSFER_SFTP_REMOTE_ROOT=/nexora_sync

    # EMAIL
    NEXORA_FILE_TRANSFER_SMTP_HOST=..., _SMTP_PORT=587, _USERNAME=...,
    NEXORA_FILE_TRANSFER_PASSWORD_ENV=NEXORA_SMTP_PASSWORD
    NEXORA_FILE_TRANSFER_IMAP_HOST=..., _IMAP_PORT=993, _IMAP_FOLDER=INBOX
    NEXORA_FILE_TRANSFER_DEFAULT_STORE_ADDRESS=...
"""
import os


def enabled():
    return os.getenv("NEXORA_FILE_TRANSFER_ENABLED", "false").lower() in ("1", "true", "yes")


def tick_seconds():
    return int(os.getenv("NEXORA_FILE_TRANSFER_TICK_SECONDS", "60"))


def transport_config():
    mode = os.getenv("NEXORA_FILE_TRANSFER_MODE", "FILE_DROP").upper()
    cfg = {"mode": mode}
    if mode == "FILE_DROP":
        cfg["file_drop"] = {"root": os.getenv("NEXORA_FILE_TRANSFER_ROOT", "")}
    elif mode == "SFTP":
        cfg["sftp"] = {
            "host": os.getenv("NEXORA_FILE_TRANSFER_SFTP_HOST"),
            "port": os.getenv("NEXORA_FILE_TRANSFER_SFTP_PORT", "22"),
            "username": os.getenv("NEXORA_FILE_TRANSFER_SFTP_USERNAME"),
            "key_path": os.getenv("NEXORA_FILE_TRANSFER_SFTP_KEY_PATH"),
            "password_env": os.getenv("NEXORA_FILE_TRANSFER_SFTP_PASSWORD_ENV"),
            "remote_root": os.getenv("NEXORA_FILE_TRANSFER_SFTP_REMOTE_ROOT", "/nexora_sync"),
        }
    elif mode == "EMAIL":
        cfg["email"] = {
            "smtp_host": os.getenv("NEXORA_FILE_TRANSFER_SMTP_HOST"),
            "smtp_port": os.getenv("NEXORA_FILE_TRANSFER_SMTP_PORT", "587"),
            "imap_host": os.getenv("NEXORA_FILE_TRANSFER_IMAP_HOST"),
            "imap_port": os.getenv("NEXORA_FILE_TRANSFER_IMAP_PORT", "993"),
            "imap_folder": os.getenv("NEXORA_FILE_TRANSFER_IMAP_FOLDER", "INBOX"),
            "username": os.getenv("NEXORA_FILE_TRANSFER_USERNAME"),
            "password_env": os.getenv("NEXORA_FILE_TRANSFER_PASSWORD_ENV"),
            "default_store_address": os.getenv("NEXORA_FILE_TRANSFER_DEFAULT_STORE_ADDRESS"),
        }
    return cfg
