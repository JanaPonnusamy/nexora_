"""Nexora Store Agent Setup Wizard.

A single packaged application (NexoraStoreAgentSetup.exe) that deploys the
Store Agent to any store: pick HO + tenant + store, download configuration
from HO, install runtime files, register and start the Windows service, then
validate end-to-end. No STORE_ID / TENANT_ID / HO_URL is hardcoded.
"""

__version__ = "1.0.0"

SERVICE_NAME = "NexoraStoreAgent"
SERVICE_DISPLAY_NAME = "Nexora Store Agent"
AGENT_EXE_NAME = "NexoraStoreAgent.exe"
SETTINGS_EXE_NAME = "NexoraStoreAgentSettings.exe"
CONFIG_FILE_NAME = "agent_config.json"
