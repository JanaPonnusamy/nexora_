"""Read/write helpers for the deployed ``agent_config.json``.

This is the single local source of agent identity. The runtime agent reads it
through ``store_agent.config`` (via $NEXORA_AGENT_CONFIG / install path).
"""
import json
from pathlib import Path

CONFIG_FILE_NAME = "agent_config.json"

# Keys persisted in agent_config.json.
FIELDS = (
    "ho_url",
    "ho_urls",
    "tenant_id",
    "tenant_name",
    "store_id",
    "store_name",
    "store_code",
    "install_path",
    "log_level",
)


def config_path(install_path):
    return Path(install_path) / CONFIG_FILE_NAME


def _url_list(primary, fallback_urls):
    """Ordered, de-duplicated route list — the primary (reachable-from-here) URL
    first, then each fallback. The runtime tries them in order and fails over."""
    urls = []

    def add(value):
        u = (value or "").strip().rstrip("/")
        if u and u not in urls:
            urls.append(u)

    add(primary)
    if isinstance(fallback_urls, (list, tuple)):
        for v in fallback_urls:
            add(v)
    elif fallback_urls:
        for part in str(fallback_urls).split(","):
            add(part)
    return urls


def build_config(ho_url, tenant, store, install_path, log_level="INFO",
                 fallback_urls=None):
    """Assemble the config dict from selected tenant/store records.

    ``fallback_urls`` (list or comma-separated string) are additional HO routes
    — e.g. a public domain and a static IP — written as ``ho_urls`` with the
    primary first. ``ho_url`` is kept for back-compat with older agents.
    """
    urls = _url_list(ho_url, fallback_urls)
    return {
        "ho_url": urls[0],
        "ho_urls": urls,
        "tenant_id": tenant.get("tenant_id"),
        "tenant_name": tenant.get("tenant_name") or tenant.get("tenant_code"),
        "store_id": store.get("store_id"),
        "store_name": store.get("store_name"),
        "store_code": store.get("store_code"),
        "install_path": str(install_path),
        "log_level": log_level,
    }


def write_config(install_path, config):
    path = config_path(install_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def read_config(install_path):
    path = config_path(install_path)
    if not path.is_file():
        raise FileNotFoundError(f"agent_config.json not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))
