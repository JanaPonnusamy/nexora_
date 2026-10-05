"""Multi-store runtime: ONE agent process serving N stores.

Activated only when the agent is in device mode (agent_config.json has
"mode":"device"); the legacy single-store run_agent.main() path is untouched.

The device authenticates to HO with its Ed25519 key (device_client) and pulls
its assigned stores from GET /api/agent/stores each sync cycle. That per-cycle
fetch IS the "confirm store credentials every sync" requirement: a credential
change / added store / removed store made in HO is picked up automatically next
cycle with no visit to the store machine.

Traffic is scheduled: stores are synced sequentially with a small stagger so N
databases + HO are not all hit at once. Each per-store sync is fully isolated
(its own connection, its own store-scoped SQLite cache) and can never break the
loop or another store's sync -- same fail-soft contract as the single-store
agent.
"""
import threading
import time
import traceback

from store_agent import config
from store_agent.device_client import DeviceIdentity
from store_agent.fernet_key_service import FernetKeyService
from store_agent.store_agent_config_decryption_service import (
    StoreAgentConfigDecryptionService,
)
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.services.heartbeat_service import HeartbeatService
from store_agent.services.sync_runtime_orchestrator import SyncRuntimeOrchestrator
from store_agent.services.sqlite_cache_service import SqliteCacheService
from store_agent.services.maintenance_service import start_cache_maintenance_thread

HEARTBEAT_SECONDS = 30
SYNC_POLL_SECONDS = 60
# Spread per-store sync starts so N stores don't hit HO / their DBs at once.
INTER_STORE_STAGGER_SECONDS = 3
# Re-fetch the assigned-store list (with fresh credentials) at most this often.
STORE_REFRESH_SECONDS = 60

_LOCKED_LICENSE_STATES = ("trial_expired", "revoked")


def _safe_tb():
    try:
        return traceback.format_exc()
    except Exception:
        return "<traceback unavailable>"


def _log(message):
    try:
        print(message, flush=True)
    except Exception:
        pass


def store_to_runtime_config(store, key):
    """Map one /api/agent/stores entry to the runtime_config dict the rest of
    the agent expects (same shape RuntimeConfigurationLoader.load produces),
    decrypting the DB password with the shared Fernet key."""
    enc = store.get("password_encrypted")
    sql_password = None
    if enc:
        sql_password = StoreAgentConfigDecryptionService().decrypt_password(
            bytes.fromhex(enc), key
        )
    return {
        "store_id": store.get("store_id"),
        "tenant_id": store.get("tenant_id"),
        "sql_server": store.get("server_name"),
        "database_name": store.get("database_name"),
        "sql_username": store.get("username"),
        "sql_password": sql_password,
        "connection_type": store.get("connection_type"),
        "is_active": store.get("is_active"),
    }


class _StoreRegistry:
    """Thread-safe holder for the current assigned-store runtime configs, shared
    between the sync loop (which refreshes it) and the heartbeat loop."""

    def __init__(self):
        self._lock = threading.Lock()
        self._by_id = {}

    def replace(self, runtime_configs):
        with self._lock:
            self._by_id = {rc["store_id"]: rc for rc in runtime_configs if rc.get("store_id")}

    def all(self):
        with self._lock:
            return list(self._by_id.values())


def _license_locked(cache):
    return cache.get_config("license_state") in _LOCKED_LICENSE_STATES


def _sync_one_store(runtime_config, ho_url):
    """One store's sync cycle. Never raises. Returns a short result string."""
    store_id = runtime_config.get("store_id")
    if not runtime_config.get("is_active"):
        return f"{store_id}: inactive, skipped"
    connection = None
    try:
        context = RuntimeContextFactory().create(runtime_config)
        connection = RuntimeSqlConnectionService().connect(context)
        orchestrator = SyncRuntimeOrchestrator(
            connection=connection, ho_api_url=ho_url, store_id=store_id,
        )
        result = orchestrator.run_cycle()
        if result.get("tasks_processed"):
            return f"{store_id}: {result}"
        return f"{store_id}: idle"
    except Exception:
        _log(f"[SYNC] store {store_id} failed:\n" + _safe_tb())
        return f"{store_id}: ERROR"
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _heartbeat_loop(registry):
    """Beat + license-checkin for every assigned store each cycle. Independent
    of sync; never raises out of the loop."""
    while True:
        for rc in registry.all():
            store_id = rc.get("store_id")
            try:
                HeartbeatService(
                    config.active_ho_url(), store_id,
                    connection_type=rc.get("connection_type"),
                ).beat()
            except Exception:
                _log(f"[HEARTBEAT] store {store_id} failed")
                config.mark_ho_failure()
            try:
                cache = SqliteCacheService(store_id=store_id)
                status = HeartbeatService(
                    config.active_ho_url(), store_id,
                    connection_type=rc.get("connection_type"),
                ).license_status()
                cache.set_config("license_state", status.get("license_state"))
            except Exception:
                pass
        time.sleep(HEARTBEAT_SECONDS)


def _refresh_stores(device, registry, key):
    """Pull the assigned stores (with fresh credentials) from HO and update the
    registry. Fail-soft: on error the last-known set stays in use."""
    try:
        stores = device.fetch_assigned_stores(config.active_ho_url())
    except Exception:
        _log("[STORES] refresh failed, using last-known set:\n" + _safe_tb())
        return None
    runtime_configs = [store_to_runtime_config(s, key) for s in stores]
    registry.replace(runtime_configs)
    return runtime_configs


def run_multi_store():
    device = DeviceIdentity(config.DEVICE_STATE_DIR)
    if not device.is_registered():
        _log("[AGENT] device not registered yet - run setup/login first. Idling.")
        # Idle instead of crash-looping so the service stays up until registered.
        while not device.is_registered():
            time.sleep(HEARTBEAT_SECONDS)

    _log("[AGENT] device mode; device_id=" + str(device.device_id()))
    _log("[AGENT] HO routes: " + ", ".join(config.HO_API_URLS))

    key = FernetKeyService().load_key()
    registry = _StoreRegistry()

    # Startup: block (with backoff) until HO answers with our store list.
    while _refresh_stores(device, registry, key) is None:
        config.mark_ho_failure()
        time.sleep(HEARTBEAT_SECONDS)
    _log("[AGENT] assigned stores: " + ", ".join(rc["store_id"] for rc in registry.all()))

    # Register each store once at startup (best-effort; heartbeat loop retries).
    for rc in registry.all():
        try:
            HeartbeatService(
                config.active_ho_url(), rc["store_id"],
                connection_type=rc.get("connection_type"),
            ).register()
        except Exception:
            _log(f"[AGENT] register store {rc['store_id']} failed (will retry)")

    threading.Thread(target=_heartbeat_loop, args=(registry,), daemon=True).start()

    # Keep the shared SQLite cache trimmed + VACUUMed so it never bloats across
    # N stores. One pass covers every store's rows in the shared DB.
    start_cache_maintenance_thread(SqliteCacheService().db_path, log=_log)

    last_store_refresh = time.time()
    while True:
        # Keep HO routes fresh so a moved HO is followed automatically.
        config.refresh_routes_from_ho()

        # Per-cycle credential/assignment confirm.
        if time.time() - last_store_refresh >= STORE_REFRESH_SECONDS:
            if _refresh_stores(device, registry, key) is not None:
                last_store_refresh = time.time()

        ho_url = config.active_ho_url()
        for rc in registry.all():
            cache = SqliteCacheService(store_id=rc["store_id"])
            if _license_locked(cache):
                _log(f"[SYNC] store {rc['store_id']} skipped: license "
                     + str(cache.get_config("license_state")))
                continue
            result = _sync_one_store(rc, ho_url)
            if not result.endswith(": idle"):
                _log("[SYNC] " + result)
            if result.endswith(": ERROR"):
                config.mark_ho_failure()
            time.sleep(INTER_STORE_STAGGER_SECONDS)

        time.sleep(SYNC_POLL_SECONDS)
