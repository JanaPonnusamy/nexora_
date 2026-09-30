"""Selects an HO-side receiver transport from config -- mirrors
store_agent/file_transfer/transport_factory.py's mode switch."""
from modules.sync.file_transfer_transport.file_drop import FileDropReceiverTransport
from modules.sync.file_transfer_transport.sftp import SftpReceiverTransport
from modules.sync.file_transfer_transport.email import EmailReceiverTransport

_MODES = ("FILE_DROP", "SFTP", "EMAIL")


def build_receiver_transport(transport_cfg):
    mode = (transport_cfg.get("mode") or "FILE_DROP").upper()
    if mode == "FILE_DROP":
        cfg = transport_cfg.get("file_drop") or {}
        root = cfg.get("root")
        if not root:
            raise ValueError("file_drop transport config requires 'root'")
        return FileDropReceiverTransport(root)
    if mode == "SFTP":
        return SftpReceiverTransport(transport_cfg.get("sftp") or {})
    if mode == "EMAIL":
        return EmailReceiverTransport(transport_cfg.get("email") or {})
    raise ValueError("Unknown file_transfer transport mode '%s' (expected one of %s)"
                     % (mode, ", ".join(_MODES)))
