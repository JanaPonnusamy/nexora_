"""HTTP client for the Nexora HO API used by the setup wizard.

Endpoints (read-only against HO; nothing here mutates the sync runtime):
  GET  /health
  GET  /api/tenants
  GET  /api/stores?tenant_id=<id>     (falls back to /api/stores/tenant/<id>)
  GET  /api/stores/{store_id}/agent-config
  POST /agent/heartbeat               (validation only)
"""
import os
import socket
from pathlib import Path

import requests
from backend.config.security import setup_access_checksum

VERSION_MARKER_NAME = "agent_version_installed.txt"


def _http_detail(ex):
    """Best-effort human-readable error including HO's JSON 'detail' body, so a
    401 shows WHY (e.g. 'Invalid setup checksum' vs 'Invalid setup credentials')
    instead of a bare 'Unauthorized'."""
    resp = getattr(ex, "response", None)
    if resp is not None:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = (resp.text or "").strip()[:200] or None
        if detail:
            return f"HTTP {resp.status_code}: {detail}"
    return str(ex)


class HoConnectionError(Exception):
    """Raised when HO cannot be reached or returns an error."""


class HoClient:
    def __init__(self, ho_url, timeout=15):
        self.base = (ho_url or "").strip().rstrip("/")
        self.timeout = timeout
        self._setup_token = None
        self._setup_username = os.getenv("NEXORA_SETUP_USERNAME", "setupdeploy")
        self._setup_password = os.getenv("NEXORA_SETUP_PASSWORD", "")

    # ---- connectivity -----------------------------------------------------

    def test_connection(self):
        """STEP 2: GET /health. Returns the parsed body on success."""
        try:
            resp = requests.get(f"{self.base}/health", timeout=self.timeout)
            resp.raise_for_status()
            body = resp.json()
        except requests.RequestException as ex:
            raise HoConnectionError(f"Cannot reach HO at {self.base}: {ex}") from ex
        except ValueError as ex:
            raise HoConnectionError(f"HO /health returned invalid JSON: {ex}") from ex
        if str(body.get("status", "")).lower() != "healthy":
            raise HoConnectionError(f"HO reported unhealthy: {body}")
        return body

    # ---- tenants ----------------------------------------------------------

    def get_tenants(self, active_only=True):
        """STEP 3: GET /api/tenants."""
        data = self._get_json("/api/tenants")
        if not isinstance(data, list):
            raise HoConnectionError("Unexpected /api/tenants response")
        if active_only:
            data = [t for t in data if t.get("is_active", True)]
        return data

    # ---- stores -----------------------------------------------------------

    def get_stores(self, tenant_id, active_only=True):
        """STEP 4: GET /api/stores?tenant_id=<id>.

        Resilient to HO variations: query-param form first, then the
        /api/stores/tenant/{id} route, then full list filtered client-side.
        """
        stores = None
        try:
            stores = self._get_json(
                "/api/stores", params={"tenant_id": tenant_id}
            )
        except HoConnectionError:
            stores = None

        if isinstance(stores, list):
            scoped = [
                s for s in stores
                if not s.get("tenant_id") or s.get("tenant_id") == tenant_id
            ]
            # The plain /api/stores ignores the param and returns everything;
            # if nothing is scoped to this tenant fall through to other forms.
            if scoped:
                stores = scoped
            else:
                stores = None

        if stores is None:
            try:
                stores = self._get_json(f"/api/stores/tenant/{tenant_id}")
            except HoConnectionError:
                stores = None

        if stores is None:
            allstores = self._get_json("/api/stores")
            stores = [
                s for s in allstores
                if s.get("tenant_id") == tenant_id
            ]

        if active_only:
            stores = [s for s in stores if s.get("is_active", True)]
        return stores

    # ---- agent configuration ----------------------------------------------

    def get_agent_config(self, store_id):
        """STEP 6: GET /api/stores/{store_id}/agent-config."""
        data = self._get_json(f"/api/stores/{store_id}/agent-config")
        if not isinstance(data, dict) or data.get("error"):
            raise HoConnectionError(
                f"HO has no agent-config for store {store_id}: "
                f"{data.get('error') if isinstance(data, dict) else data}"
            )
        return data

    # ---- heartbeat (validation) -------------------------------------------

    def post_heartbeat(self, store_id, connection_type=None,
                       agent_version=None):
        """STEP 10: confirm the HO heartbeat write path is reachable."""
        try:
            ip_address = socket.gethostbyname(socket.gethostname())
        except OSError:
            ip_address = None
        if not agent_version:
            install = os.environ.get("NEXORA_INSTALL_PATH")
            marker = Path(install) / VERSION_MARKER_NAME if install else None
            if marker and marker.is_file():
                try:
                    agent_version = marker.read_text(encoding="utf-8").strip() or None
                except OSError:
                    agent_version = None
        payload = {
            "store_id": store_id,
            "agent_version": agent_version or "1.0.0",
            "connection_type": connection_type,
            "ip_address": ip_address,
        }
        try:
            resp = requests.post(
                f"{self.base}/agent/heartbeat", json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as ex:
            raise HoConnectionError(f"Heartbeat to HO failed: {ex}") from ex
        except ValueError:
            return {"status": "ok"}

    # ---- internals --------------------------------------------------------

    def _get_json(self, path, params=None):
        try:
            resp = requests.get(
                f"{self.base}{path}", params=params, timeout=self.timeout,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as ex:
            raise HoConnectionError(f"GET {path} failed: {_http_detail(ex)}") from ex
        except ValueError as ex:
            raise HoConnectionError(f"GET {path} invalid JSON: {ex}") from ex

    def _headers(self):
        if not self._setup_token:
            self._setup_token = self._fetch_setup_token()
        return {"X-Nexora-Setup-Token": self._setup_token}

    def _fetch_setup_token(self):
        if not self._setup_password:
            raise HoConnectionError(
                "NEXORA_SETUP_PASSWORD is not configured for the setup tool"
            )
        try:
            resp = requests.post(
                f"{self.base}/api/auth/setup-login",
                json={
                    "username": self._setup_username,
                    "password": self._setup_password,
                },
                headers={
                    "X-Nexora-Setup-Checksum": setup_access_checksum(
                        self._setup_username,
                        self._setup_password,
                        allowed_paths=[
                            "/api/tenants",
                            "/api/stores",
                            "/api/stores/tenant/{tenant_id}",
                            "/api/stores/{store_id}/agent-config",
                        ],
                    )
                },
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as ex:
            raise HoConnectionError(
                f"Setup login failed: {_http_detail(ex)}") from ex
        except ValueError as ex:
            raise HoConnectionError(f"Setup login returned invalid JSON: {ex}") from ex
        token = data.get("token")
        if not token:
            raise HoConnectionError("Setup login returned no token")
        return token
