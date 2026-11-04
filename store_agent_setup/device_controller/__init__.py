"""Nexora Device Controller -- one SYSTEM service per PC that replaces every
per-app watchdog and lets HO manage all Nexora apps on the machine.

Manages: Store Agent (+ its HO links), Mail Transfer, Stock Client (GUI),
HO Backend (UniNexHO on HO nodes) and itself. HO talks to it only through
signed messages (see backend/modules/device_controller/protocol.py); the
controller dials OUT to HO (long-poll), so no inbound port is opened.
"""
import os
from pathlib import Path

CONTROLLER_VERSION = "1.0.6"

SERVICE_NAME = "NexoraDeviceController"
SERVICE_DISPLAY_NAME = "Nexora Device Controller"
SERVICE_DESCRIPTION = (
    "Keeps Nexora apps (Store Agent, Stock Client, HO Backend) running and up "
    "to date as HO directs, and hosts HO-audited remote maintenance sessions."
)
EXE_NAME = "NexoraDeviceController.exe"

_PROGRAM_FILES = Path(os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files")
INSTALL_DIR = _PROGRAM_FILES / "Nexora" / "DeviceController"

_PROGRAMDATA = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
STATE_DIR = _PROGRAMDATA / "Nexora" / "DeviceController"
PRIVATE_DIR = STATE_DIR / "private"          # SYSTEM + Administrators only
INBOX_DIR = STATE_DIR / "inbox"              # Users may write (Stock Client enrollment)
CONFIG_FILE = PRIVATE_DIR / "controller.json"
SEEN_FILE = PRIVATE_DIR / "seen_messages.json"
PUBLIC_KEY_FILE = STATE_DIR / "device_public_key.pem"
FINGERPRINT_FILE = STATE_DIR / "device_fingerprint.txt"
STATUS_FILE = STATE_DIR / "status.json"
LOG_FILE = STATE_DIR / "controller.log"
STAGING_DIR = PRIVATE_DIR / "staging"
BACKUP_DIR = PRIVATE_DIR / "backups"

# Services/tasks the controller supersedes (retired on first start).
LEGACY_WATCHDOG_SERVICES = ("NexoraStoreAgentWatchdog", "NexoraStockClientWatchdog")
LEGACY_WATCHDOG_TASKS = ("NexoraHOWatchdog", "NexoraBackendWatchdog")
HO_MAINTENANCE_FLAG = _PROGRAMDATA / "NexoraHO" / "maintenance.flag"
