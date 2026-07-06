"""Store-agent runtime identity.

Values are resolved at import time from the deployed ``agent_config.json`` so the
SAME packaged agent works for every store with NO hardcoded STORE_ID / HO_URL.

Resolution order (first hit wins):
  1. $NEXORA_AGENT_CONFIG          -> explicit path to agent_config.json
  2. $NEXORA_INSTALL_PATH/agent_config.json
  3. <install root>/agent_config.json   (parent of this package)
  4. built-in development defaults (used by local dev + tests only)

Multiple HO URLs
----------------
A store can reach Head Office by more than one route (local LAN IP, a public
domain via a tunnel, a static IP, ...). Configure them all and the agent uses
whichever is reachable, failing over automatically:

    { "store_id": "...", "ho_urls": ["http://192.168.10.80:8000",
                                     "https://ho.example.com",
                                     "http://203.0.113.10:8000"] }

Back-compat: a single ``ho_url`` string still works, and it may be a
comma-separated list. The environment variable ``NEXORA_HO_URLS`` (comma
separated) overrides the file. The FIRST candidate is tried first, so put the
LAN URL first for local stores.
"""
import json
import os
import threading
from pathlib import Path

# Development fallbacks (used only when no agent_config.json is deployed).
_DEFAULTS = {
    "store_id": "FCBE8B35-B1A1-463E-80C6-73161CDC8F32",
    "ho_url": "http://127.0.0.1:8000",
}


def _candidate_paths():
    env_file = os.environ.get("NEXORA_AGENT_CONFIG")
    if env_file:
        yield Path(env_file)
    install = os.environ.get("NEXORA_INSTALL_PATH")
    if install:
        yield Path(install) / "agent_config.json"
    here = Path(__file__).resolve().parent
    # agent_config.json deployed alongside the package or at the install root.
    yield here / "agent_config.json"
    yield here.parent / "agent_config.json"


def _load_agent_config():
    for path in _candidate_paths():
        try:
            if path and path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def _normalize_url(value):
    return (value or "").strip().rstrip("/")


def _candidate_urls(cfg):
    """Ordered, de-duplicated list of HO base URLs to try (first = preferred)."""
    out = []

    def add(value):
        url = _normalize_url(value)
        if url and url not in out:
            out.append(url)

    # 1) Environment override (comma separated) wins for ops overrides.
    env = os.environ.get("NEXORA_HO_URLS") or os.environ.get("NEXORA_HO_URL")
    if env:
        for part in env.split(","):
            add(part)

    # 2) Preferred: an explicit list of URLs.
    for value in (cfg.get("ho_urls") or []):
        add(value)

    # 3) Back-compat: a single ho_url, possibly comma-separated.
    raw = cfg.get("ho_url")
    if isinstance(raw, list):
        for value in raw:
            add(value)
    elif raw:
        for part in str(raw).split(","):
            add(part)

    if not out:
        add(_DEFAULTS["ho_url"])
    return out


_CFG = _load_agent_config()

SQL_SERVER = ""
SQL_DATABASE = ""
SQL_USERNAME = ""
SQL_PASSWORD = ""

STORE_ID = _CFG.get("store_id") or _DEFAULTS["store_id"]

# All configured HO routes, and a back-compat single value (the first/preferred).
HO_API_URLS = _candidate_urls(_CFG)
HO_API_URL = HO_API_URLS[0]

_active_lock = threading.Lock()
_active_url = {"value": None}


def _probe(url, timeout):
    """True if the HO health endpoint answers OK at ``url``."""
    try:
        import requests
        return requests.get(url + "/health", timeout=timeout).ok
    except Exception:
        return False


def active_ho_url(force=False, timeout=3):
    """Return the first reachable HO URL, cached until :func:`mark_ho_failure`.

    With a single configured URL this returns it immediately (no network probe),
    so existing single-URL stores behave exactly as before. With several, it
    probes ``/health`` in order and remembers the winner; if none answer it
    keeps the last good one (or the first candidate) rather than blocking.
    """
    with _active_lock:
        if _active_url["value"] and not force:
            return _active_url["value"]
        if len(HO_API_URLS) == 1:
            _active_url["value"] = HO_API_URLS[0]
            return _active_url["value"]
        for url in HO_API_URLS:
            if _probe(url, timeout):
                _active_url["value"] = url
                return url
        _active_url["value"] = _active_url["value"] or HO_API_URLS[0]
        return _active_url["value"]


def mark_ho_failure():
    """Force the next :func:`active_ho_url` call to re-probe (failover)."""
    with _active_lock:
        _active_url["value"] = None
