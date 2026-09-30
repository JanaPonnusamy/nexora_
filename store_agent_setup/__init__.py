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
