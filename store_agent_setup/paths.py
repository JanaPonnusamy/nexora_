"""Resource resolution that works in both source and PyInstaller-frozen modes.

When frozen, bundled data lives under ``sys._MEIPASS``. In source mode it lives
in the repository tree. ``resource_root`` returns whichever applies so the same
code finds the agent runtime, the fernet key and the agent service binary.
"""
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
    """STEP 5 logic: prefer D:\\ when present, else C:\\."""
    if Path("D:/").exists():
        return r"D:\NexoraStoreAgent"
    return r"C:\NexoraStoreAgent"
