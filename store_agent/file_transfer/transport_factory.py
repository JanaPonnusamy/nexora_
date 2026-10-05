"""Selects a transport implementation from config. Adding a new physical
channel later means adding one adapter module + one branch here -- nothing
else in the sync engine, package builder, or HO importer changes."""

from store_agent.file_transfer.file_drop_transport import FileDropSenderTransport
from store_agent.file_transfer.sftp_transport import SftpSenderTransport
from store_agent.file_transfer.email_transport import EmailSenderTransport

_MODES = ("FILE_DROP", "SFTP", "EMAIL")


def build_sender_transport(transport_cfg, store_id):
    mode = (transport_cfg.get("mode") or "FILE_DROP").upper()
    if mode == "FILE_DROP":
        cfg = transport_cfg.get("file_drop") or {}
        root = cfg.get("root")
        if not root:
            raise ValueError("file_drop transport config requires 'root'")
        return FileDropSenderTransport(root, store_id)
    if mode == "SFTP":
        return SftpSenderTransport(transport_cfg.get("sftp") or {}, store_id)
    if mode == "EMAIL":
        return EmailSenderTransport(transport_cfg.get("email") or {}, store_id)
    raise ValueError("Unknown file_transfer transport mode '%s' (expected one of %s)"
                     % (mode, ", ".join(_MODES)))
