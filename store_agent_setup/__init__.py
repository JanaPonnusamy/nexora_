"""Nexora Store Agent Setup Wizard.

A single packaged application (NexoraStoreAgentSetup.exe) that deploys the
Store Agent to any store: pick HO + tenant + store, download configuration
from HO, install runtime files, register and start the Windows service, then
validate end-to-end. No STORE_ID / TENANT_ID / HO_URL is hardcoded.
"""

__version__ = "1.0.0"
AGENT_VERSION = __version__

SERVICE_NAME = "NexoraStoreAgent"
SERVICE_DISPLAY_NAME = "Nexora Store Agent"
AGENT_EXE_NAME = "NexoraStoreAgent.exe"
SETTINGS_EXE_NAME = "NexoraStoreAgentSettings.exe"
CONFIG_FILE_NAME = "agent_config.json"

# Always-on companion service: reconciles NexoraStoreAgent's run-state and
# installed version against what HO wants (see modules/agent_ops on the
# backend), so a stop/start/update can be issued from HO instead of requiring
# someone at the store PC. Separate from SERVICE_NAME because a running exe
# cannot safely replace or fully restart itself.
WATCHDOG_SERVICE_NAME = "NexoraStoreAgentWatchdog"
WATCHDOG_DISPLAY_NAME = "Nexora Store Agent Watchdog"
WATCHDOG_EXE_NAME = "NexoraStoreAgentWatchdog.exe"
WATCHDOG_VERSION = "1.0.0"

# Phase 2 extraction: EMAIL package delivery (SMTP send + IMAP ACK poll) runs
# as its own always-on service, separate from NexoraStoreAgent (which keeps
# building packages) -- only relevant to stores configured for
# file_transfer.transport.mode == EMAIL; installing/starting it is opt-in via
# NexoraStoreAgentSettings, not part of the default DIRECT_HTTP wizard flow.
MAIL_TRANSFER_SERVICE_NAME = "NexoraMailTransfer"
MAIL_TRANSFER_DISPLAY_NAME = "Nexora Mail Transfer"
MAIL_TRANSFER_EXE_NAME = "NexoraMailTransfer.exe"
MAIL_TRANSFER_VERSION = "1.0.0"

# Milestone 2: the Axythic Supplier Stock Client (an Electron GUI, per-user
# install) cannot stop/replace/relaunch itself, and -- unlike the store agent --
# it is NOT a Windows service, so there is nothing for HO to sc-start once it is
# closed. This always-on SYSTEM service polls HO (modules/stock_client_ops) for
# the version authorized for THIS machine's store, verifies the signed package,
# closes the GUI by its exact install path, runs the installer silently in the
# logged-in user's session (WTS/CreateProcessAsUser), health-checks, rolls back
# on failure, and heartbeats fleet status. Separate from everything above
# because a running GUI cannot update itself and a SYSTEM service cannot BE the
# GUI (hence the split watchdog_status / client_status in the heartbeat).
STOCK_CLIENT_WATCHDOG_SERVICE_NAME = "NexoraStockClientWatchdog"
STOCK_CLIENT_WATCHDOG_DISPLAY_NAME = "Nexora Stock Client Watchdog"
STOCK_CLIENT_WATCHDOG_EXE_NAME = "NexoraStockClientWatchdog.exe"
STOCK_CLIENT_WATCHDOG_VERSION = "1.0.0"
# The installed Electron app's product name (electron-builder `productName`);
# the GUI exe is "<product>.exe" under the per-user install root.
STOCK_CLIENT_PRODUCT_NAME = "Axythic Supplier Stock"
