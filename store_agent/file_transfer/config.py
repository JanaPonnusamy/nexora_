"""FILE_TRANSFER mode configuration, read from the optional "file_transfer"
block in agent_config.json::

    {
      "store_id": "...", "ho_urls": [...],
      "file_transfer": {
        "enabled": true,
        "interval_seconds": 1800,
        "mail_transfer_interval_seconds": 300,
        "transport": {
          "mode": "FILE_DROP",
          "file_drop": {"root": "\\\\\\\\fileserver\\\\nexora_sync"},
          "sftp": {"host": "...", "port": 22, "username": "...",
                   "key_path": "...", "password_env": "NEXORA_SFTP_PASSWORD",
                   "remote_root": "/nexora_sync"},
          "email": {"smtp_host": "...", "smtp_port": 587, "username": "...",
                     "password_env": "NEXORA_SMTP_PASSWORD",
                     "to_address": "sync@ho.example.com",
                     "imap_host": "...", "imap_folder": "INBOX",
                     "max_attachment_bytes": 20971520}
        }
      }
    }

Credentials are never embedded in the file directly -- every secret is a
"*_env" key naming an environment variable to read at connect time.

``mail_transfer_interval_seconds`` (EMAIL transport only) is read by the
standalone NexoraMailTransfer process (store_agent/mail_transfer_main.py),
not by the main agent process -- it governs how often that separate process
sends the outbox and polls IMAP for ACKs, independent of (and normally much
shorter than) ``interval_seconds``, which governs how often the main agent
process builds a new package.
"""
import os
from pathlib import Path

from store_agent import config as agent_config

DEFAULT_INTERVAL_SECONDS = 1800  # ~30 minutes per objective 5/12
DEFAULT_MAIL_TRANSFER_INTERVAL_SECONDS = 300  # ~5 minutes


def file_transfer_config():
    cfg = (agent_config.raw_config().get("file_transfer") or {})
    interval = os.environ.get("NEXORA_FILE_TRANSFER_INTERVAL_SECONDS")
    mail_interval = os.environ.get("NEXORA_MAIL_TRANSFER_INTERVAL_SECONDS")
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "interval_seconds": int(interval) if interval else int(
            cfg.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
        ),
        "mail_transfer_interval_seconds": int(mail_interval) if mail_interval else int(
            cfg.get("mail_transfer_interval_seconds", DEFAULT_MAIL_TRANSFER_INTERVAL_SECONDS)
        ),
        "transport": cfg.get("transport") or {},
    }


def outbox_root():
    install_path = os.environ.get("NEXORA_INSTALL_PATH")
    if install_path:
        return Path(install_path) / "outbox"
    return Path(__file__).resolve().parent.parent / "config_cache" / "outbox"
