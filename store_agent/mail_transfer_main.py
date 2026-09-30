"""Standalone entrypoint for NexoraMailTransfer.exe (Phase 2 extraction).

Owns EMAIL package *delivery* only: sending whatever the main Store Agent
process (store_agent.run_agent) has already built and durably queued in the
shared SQLite outbox, and polling IMAP for HO's ACK back. It never touches
SQL extraction, hashing, chunking, or package building -- that stays in
run_agent.py so there is exactly one place a package is ever assembled,
regardless of which process ends up sending it.

Both processes share the same on-disk state:
  - SqliteCacheService(store_id=STORE_ID) resolves the same store_agent.db
    (NEXORA_INSTALL_PATH-anchored) the main agent uses -- WAL mode + a
    30s busy timeout on every connection already make it safe for two
    processes to read/write it concurrently (see SqliteCacheService._connect).
  - FileTransferOutbox resolves the same outbox root (pending/sending/sent/
    failed folders) via store_agent.file_transfer.config.outbox_root().

Runnable directly for development:
    python -m store_agent.mail_transfer_main
Packaged as NexoraMailTransfer.exe via store_agent_setup.build.build_mail_transfer()
and hosted as a Windows service by store_agent_setup.mail_transfer_service.
"""
import time
import traceback

from store_agent.config import STORE_ID
from store_agent.file_transfer import config as file_transfer_config
from store_agent.file_transfer.outbox import FileTransferOutbox
from store_agent.file_transfer.sync_dispatcher import FileTransferSyncDispatcher
from store_agent.file_transfer.transport_factory import build_sender_transport
from store_agent.services.sqlite_cache_service import SqliteCacheService

def _safe_tb():
    try:
        return traceback.format_exc()
    except Exception:
        return "<traceback unavailable>"


def _log(message):
    try:
        print(message, flush=True)
    except Exception:
        pass


def _poll_seconds():
    ft_cfg = file_transfer_config.file_transfer_config()
    return int(ft_cfg["mail_transfer_interval_seconds"])


def _require_email_transport(ft_cfg):
    mode = (ft_cfg.get("transport") or {}).get("mode", "").upper()
    if mode != "EMAIL":
        raise RuntimeError(
            "NexoraMailTransfer is an EMAIL-transport-only delivery service; "
            "agent_config.json file_transfer.transport.mode is %r, not "
            "'EMAIL'. Nothing to do -- for FILE_DROP/SFTP, delivery already "
            "runs inside the main Store Agent process." % mode
        )


def run_cycle(cache):
    """One send+ack cycle. Never raises -- same contract as run_agent.py's
    cycle functions, since this runs unattended as a Windows service."""
    try:
        ft_cfg = file_transfer_config.file_transfer_config()
        _require_email_transport(ft_cfg)
        outbox = FileTransferOutbox(cache, file_transfer_config.outbox_root())
        sender = build_sender_transport(ft_cfg["transport"], STORE_ID)
        dispatcher = FileTransferSyncDispatcher(None, outbox, sender)
        result = dispatcher.run_delivery_only()
        _log("[MAIL_TRANSFER] cycle: " + str(result))
        return result
    except Exception:
        _log("[MAIL_TRANSFER] cycle failed:\n" + _safe_tb())
        return {"error": True}


def main():
    _log("[MAIL_TRANSFER] starting for store " + str(STORE_ID))
    cache = SqliteCacheService(store_id=STORE_ID)
    while True:
        run_cycle(cache)
        time.sleep(_poll_seconds())


if __name__ == "__main__":
    main()
