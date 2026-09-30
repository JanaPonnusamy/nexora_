"""UniNex HO Setup Installer.

A single packaged application (HO_Setup.exe) that deploys the UniNex Head
Office (HO) backend + frontend to a fresh tenant machine:

  1. Welcome
  2. License
  3. Installation folder
  4. SQL Server configuration (+ Test Connection)
  5. Database deployment (restore bundled NEXORA_PLATFORM.bak)
  6. Generate production configuration
  7. Install backend files
  8. Install + start the Windows service
  9. Deploy the production frontend build
 10. Health check + deployment summary

The Windows-service lifecycle mirrors the proven Store Agent implementation
(sc.exe with start=auto + failure-restart actions). HO_Uninstall.exe removes the
service and application files (the SQL database is preserved unless explicitly
selected).
"""

__version__ = "1.0.0"

# --- Windows service identity ----------------------------------------------
SERVICE_NAME = "UniNexHO"
SERVICE_DISPLAY_NAME = "UniNex HO Backend"
SERVICE_DESCRIPTION = (
    "UniNex Head Office backend API (FastAPI/uvicorn) and platform services."
)

# --- Packaged executable names ---------------------------------------------
BACKEND_EXE_NAME = "HO_Backend.exe"        # Windows-service host (embedded Python)
SETUP_EXE_NAME = "HO_Setup.exe"            # the wizard
UNINSTALL_EXE_NAME = "HO_Uninstall.exe"    # the uninstaller

# Phase 2 extraction: EMAIL package receiving (IMAP poll + validate/import +
# ACK send) runs as its own always-on service, separate from UniNexHO (which
# keeps serving the API). Only relevant when NEXORA_FILE_TRANSFER_MODE=EMAIL;
# installing it is a separate, opt-in step, not part of the default HO_Setup
# wizard flow (most deployments never touch FILE_TRANSFER at all).
MAIL_RECEIVER_SERVICE_NAME = "NexoraHOMailReceiver"
MAIL_RECEIVER_DISPLAY_NAME = "Nexora HO Mail Receiver"
MAIL_RECEIVER_SERVICE_DESCRIPTION = (
    "Nexora HO Mail Receiver: polls a mailbox for FILE_TRANSFER packages, "
    "imports them through the existing staging/MERGE pipeline, and emails "
    "acknowledgements back, for stores configured with "
    "file_transfer.transport.mode = EMAIL."
)
MAIL_RECEIVER_EXE_NAME = "NexoraHOMailReceiver.exe"

# --- Deployment defaults ----------------------------------------------------
DEFAULT_INSTALL_PATH = r"C:\Program Files\UniNex\HO"
DEFAULT_DATABASE = "NEXORA_PLATFORM"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
BACKUP_FILE_NAME = "NEXORA_PLATFORM.bak"
CONFIG_DIR_NAME = "config"
ENV_FILE_NAME = "ho.env"
SETTINGS_FILE_NAME = "settings.json"

# Sub-directories created under the install root.
INSTALL_SUBDIRS = ("config", "logs", "uploads", "backups", "frontend")
