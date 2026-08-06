import os
import socket

import requests
from store_agent import config


class HeartbeatService:
    """Agent health beacon. Writes to HO store_agent_registry /
    agent_heartbeat_log via the runtime API. Never touches the store DB."""

    def __init__(self, ho_api_url, store_id, connection_type=None,
                 agent_version=None):
        self.base = ho_api_url.rstrip("/")
        self.store_id = store_id
        self.connection_type = connection_type
        self.agent_version = agent_version or config.installed_agent_version()

    def _payload(self):
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = None
        try:
            ip_address = socket.gethostbyname(hostname) if hostname else None
        except Exception:
            ip_address = None
        return {
            "store_id": self.store_id,
            "agent_version": self.agent_version,
            "connection_type": self.connection_type,
            "ip_address": ip_address,
            # Where this agent is installed, so HO can push/track updates later.
            "install_path": os.environ.get("NEXORA_INSTALL_PATH"),
            "hostname": hostname,
        }

    def register(self):
        response = requests.post(
            self.base + "/agent/register", json=self._payload(), timeout=30
        )
        response.raise_for_status()
        return response.json()

    def beat(self):
        response = requests.post(
            self.base + "/agent/heartbeat", json=self._payload(), timeout=30
        )
        response.raise_for_status()
        return response.json()
