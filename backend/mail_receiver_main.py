"""Standalone entrypoint for NexoraHOMailReceiver.exe (Phase 2 extraction).

Owns EMAIL package *receiving* only: polls the configured HO mailbox for
incoming NEXORA-SYNC packages, validates/imports them through the EXISTING
receiver pipeline (modules.sync.file_transfer_receiver_service -- checksum,
manifest, duplicate check, staging, MERGE via runtime_repository.upload_chunk,
exactly the same code path FILE_DROP/SFTP use), and emails the ACK back. It
is a second HOST for modules.sync.file_transfer_scheduler.run_forever(), not
a second implementation of receiving.

Runnable directly for development (backend/ on sys.path, same convention as
launch_ho_service.py):
    python backend/mail_receiver_main.py
Packaged as NexoraHOMailReceiver.exe via ho_setup.build and hosted as a
Windows service by ho_setup.mail_receiver_service.

Requires NEXORA_FILE_TRANSFER_ENABLED=true and
NEXORA_FILE_TRANSFER_MODE=EMAIL (see modules/sync/file_transfer_config.py) --
refuses to run otherwise, since for FILE_DROP/SFTP the in-process FastAPI
receiver thread already handles polling and running this too would create a
second, redundant poller.
"""
import os
import sys
import threading

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def main():
    from modules.sync import file_transfer_config as cfg
    from modules.sync import file_transfer_scheduler as scheduler

    if not cfg.enabled():
        raise SystemExit(
            "NEXORA_FILE_TRANSFER_ENABLED is not set -- nothing for "
            "NexoraHOMailReceiver to do."
        )
    mode = cfg.transport_config().get("mode")
    if mode != "EMAIL":
        raise SystemExit(
            "NexoraHOMailReceiver is an EMAIL-transport-only receiver; "
            "NEXORA_FILE_TRANSFER_MODE is %r, not 'EMAIL'. For FILE_DROP/SFTP, "
            "the in-process HO backend receiver thread already handles this "
            "(see api/app.py _start_file_transfer_receiver_on_startup)." % mode
        )
    scheduler.run_forever(threading.Event())


if __name__ == "__main__":
    main()
