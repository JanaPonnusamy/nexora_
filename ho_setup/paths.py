"""Resource resolution for both source and PyInstaller-frozen modes.

When frozen, bundled data lives under ``sys._MEIPASS``; in source mode it lives
in the repository tree. The same code therefore finds the backend distribution,
the frontend build and the bundled NEXORA_PLATFORM.bak in either mode.
"""
import sys
from pathlib import Path


def is_frozen():
    return getattr(sys, "frozen", False)


def resource_root():
    """Directory that contains bundled runtime resources."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    # Source mode: repo root (parent of the ho_setup package).
    return Path(__file__).resolve().parent.parent


def repo_root():
    return Path(__file__).resolve().parent.parent


def assets_dir():
    """Where the operator drops NEXORA_PLATFORM.bak before building."""
    return Path(__file__).resolve().parent / "assets"


def default_install_path():
    from . import DEFAULT_INSTALL_PATH

    return DEFAULT_INSTALL_PATH
