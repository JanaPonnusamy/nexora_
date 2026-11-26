"""Resource resolution that works in both source and PyInstaller-frozen modes.

When frozen, bundled data lives under ``sys._MEIPASS``. In source mode it lives
in the repository tree. ``resource_root`` returns whichever applies so the same
code finds the agent runtime, the fernet key and the agent service binary.
"""
import string
import sys
from pathlib import Path


def is_frozen():
    return getattr(sys, "frozen", False)


def resource_root():
    """Directory that contains bundled runtime resources."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # source mode: repo root (parent of the store_agent_setup package)
    return Path(__file__).resolve().parent.parent


def repo_root():
    return Path(__file__).resolve().parent.parent


def default_install_path():
    """Owner ruling (2026-11-24): never silently default a new install onto
    C: -- a store PC's system drive is exactly the one that keeps filling up
    (see the Node9-pc disk-space incident this ruling followed). Prefers D:
    (existing convention, e.g. D:\\NexoraStoreAgent already live on Node9-pc),
    then any other non-system drive letter present (E:, F:, ...). Only
    returns a C: path as an explicit last resort when literally no other
    fixed drive exists, and always with is_c_drive_fallback=True in that
    case so the wizard can warn the operator instead of silently proceeding
    -- this is a GUI text field the operator can always retype, so this
    changes the SUGGESTED default, never a hard block on C: itself."""
    if Path("D:/").exists():
        return r"D:\NexoraStoreAgent", False
    for letter in string.ascii_uppercase:
        if letter in ("C", "D"):
            continue
        if Path(f"{letter}:/").exists():
            return rf"{letter}:\NexoraStoreAgent", False
    return r"C:\NexoraStoreAgent", True
