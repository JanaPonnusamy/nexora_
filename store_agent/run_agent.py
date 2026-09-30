"""Production store-agent entrypoint: one process per store.

Runs two independent loops:
  - heartbeat loop (every HEARTBEAT_SECONDS) -> keeps the store ONLINE in HO
  - sync loop (every SYNC_POLL_SECONDS) -> polls + executes pending sync tasks

The heartbeat is decoupled from sync so a store stays ONLINE even when idle
or when a sync run is in progress / failing.
"""
import threading
import time
import traceback

from store_agent import config
from store_agent.config import STORE_ID
from store_agent.runtime_configuration_loader import RuntimeConfigurationLoader
from store_agent.runtime_context_factory import RuntimeContextFactory
from store_agent.runtime_sql_connection_service import RuntimeSqlConnectionService
from store_agent.services.heartbeat_service import HeartbeatService
from store_agent.services.sync_runtime_orchestrator import SyncRuntimeOrchestrator
from store_agent.services.file_transfer_runtime_orchestrator import (
    FileTransferRuntimeOrchestrator,
)
from store_agent.services.sqlite_cache_service import SqliteCacheService
from store_agent.services.catalog_delta_service import CatalogDeltaService
from store_agent.file_transfer import config as file_transfer_config
from store_agent.file_transfer.outbox import FileTransferOutbox
from store_agent.file_transfer.transport_factory import build_sender_transport
from store_agent.file_transfer.sync_dispatcher import FileTransferSyncDispatcher

HEARTBEAT_SECONDS = 30
SYNC_POLL_SECONDS = 60


def _safe_tb():
    """traceback.format_exc() that can never raise."""
    try:
        return traceback.format_exc()
    except Exception:
        return "<traceback unavailable>"


_LOCKED_LICENSE_STATES = ("trial_expired", "revoked")


def _license_locked(cache):
    """True once the heartbeat loop has observed an explicit trial_expired or
    revoked check-in response. Absent/unknown state (e.g. before the first
    successful check-in) is NOT locked -- a store must never be blocked by
    the mere absence of a license record or a transient HO outage, only by an
    explicit expired/revoked answer from HO."""
    return cache.get_config("license_state") in _LOCKED_LICENSE_STATES


def _log(message):
    """Best-effort log line that can never raise.

    A Windows service has no console and its redirected log stream can fail
    (closed/rotated/disk). Logging must never be able to kill a loop -- that
    bug is exactly what let the heartbeat thread die after a sync failure.
    """
    try:
        print(message, flush=True)
    except Exception:
        pass


def _heartbeat_loop(connection_type, cache):
    """Independent agent-health beacon. This loop must run forever regardless
    of any sync failure -- nothing inside it may propagate out of the loop.

    Each beat targets the currently-reachable HO URL; a failure rotates to the
    next configured route (LAN / domain / static IP) on the following beat.

    Also checks in against license activation on the same cadence, so a
    trial expiry/revocation (or a newly issued key unlocking the store)
    takes effect within one cycle -- no separate poll, no agent restart. A
    failed check-in (HO unreachable) is fail-soft: the last-known-good
    license_state stays cached and the sync loop keeps running on it,
    exactly like the runtime-config refresh already does."""
    while True:
        try:
            HeartbeatService(
                config.active_ho_url(), STORE_ID, connection_type=connection_type
            ).beat()
        except Exception:
            _log("[HEARTBEAT] failed:\n" + _safe_tb())
            config.mark_ho_failure()  # fail over to another HO URL next beat
        try:
            status = HeartbeatService(
                config.active_ho_url(), STORE_ID, connection_type=connection_type
            ).license_status()
            cache.set_config("license_state", status.get("license_state"))
            if status.get("license_state") in ("trial_expired", "revoked"):
                _log("[LICENSE] " + (status.get("message") or status.get("license_state")))
        except Exception:
            _log("[LICENSE] check-in failed, using cached state:\n" + _safe_tb())
        time.sleep(HEARTBEAT_SECONDS)


def _run_file_transfer_cycle(runtime_context, runtime_config, cache):
    """One FILE_TRANSFER cycle: process HO results, build at most one new
    package from current deltas, attempt to send the outbox. Never raises --
    same contract as the DIRECT_HTTP cycle below.

    EMAIL transport (Phase 2 extraction): package *delivery* (SMTP send +
    IMAP ACK poll) is owned exclusively by the standalone NexoraMailTransfer
    process against the same SQLite outbox -- this process only builds
    packages and enqueues them, so a mail-server outage never blocks sync
    extraction and there is never more than one process holding an SMTP/IMAP
    connection for this store. FILE_DROP/SFTP are unaffected: this process
    still builds AND delivers for those transports, exactly as before."""
    connection = None
    try:
        connection = RuntimeSqlConnectionService().connect(runtime_context)
        ft_cfg = file_transfer_config.file_transfer_config()
        outbox = FileTransferOutbox(cache, file_transfer_config.outbox_root())
        orchestrator = FileTransferRuntimeOrchestrator(
            connection=connection, store_id=STORE_ID,
            tenant_id=runtime_config.get("tenant_id"), cache=cache, outbox=outbox,
            agent_version=config.installed_agent_version(),
        )
        transport_mode = (ft_cfg["transport"] or {}).get("mode", "").upper()
        if transport_mode == "EMAIL":
            result = {"build": orchestrator.run_cycle(),
                      "send": "DELEGATED_TO_NexoraMailTransfer"}
        else:
            sender = build_sender_transport(ft_cfg["transport"], STORE_ID)
            result = FileTransferSyncDispatcher(orchestrator, outbox, sender).run()
        _log("[FILE_TRANSFER] cycle: " + str(result))
    except Exception:
        _log("[FILE_TRANSFER] cycle failed:\n" + _safe_tb())
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _load_runtime_config():
    """Load the store's runtime config, trying each HO route until one answers.

    Returns (runtime_config, ho_url_used). Blocks (with backoff) until HO is
    reachable so a transient outage at boot never leaves the store stuck."""
    while True:
        ho_url = config.active_ho_url()
        try:
            cfg = RuntimeConfigurationLoader().load(
                f"{ho_url}/api/stores/{STORE_ID}/agent-config"
            )
            return cfg, ho_url
        except Exception:
            _log("[AGENT] HO unreachable at " + ho_url + ", retrying:\n" + _safe_tb())
            config.mark_ho_failure()
            time.sleep(HEARTBEAT_SECONDS)


def _refresh_runtime_config(current_config, ho_url):
    """Single-attempt re-fetch of the store's runtime config from HO.

    Never blocks and never raises: a transient HO outage must keep the sync
    loop running on the last-known-good cached config rather than stall it.
    Returns ``current_config`` unchanged unless a *different* config was
    successfully fetched."""
    try:
        fresh = RuntimeConfigurationLoader().load(
            f"{ho_url}/api/stores/{STORE_ID}/agent-config"
        )
    except Exception:
        _log("[CONFIG] refresh failed, using cached config:\n" + _safe_tb())
        return current_config

    if fresh != current_config:
        _log("[CONFIG] change detected, reloading runtime context")
        return fresh
    return current_config


def main():
    # Device mode (zero-config, multi-store) delegates to the multi-store
    # runtime. The legacy single-store path below is untouched for existing
    # store_id-based deployments.
    if config.DEVICE_MODE:
        from store_agent.multi_store_runtime import run_multi_store
        return run_multi_store()

    _log("[AGENT] HO routes: " + ", ".join(config.HO_API_URLS))
    runtime_config, ho_url = _load_runtime_config()
    runtime_context = RuntimeContextFactory().create(runtime_config)

    try:
        HeartbeatService(
            ho_url, STORE_ID, connection_type=runtime_config.get("connection_type"),
        ).register()
        print("[AGENT] registered store", STORE_ID, "via", ho_url)
    except Exception:
        _log("[AGENT] register failed (heartbeat loop will retry):\n" + _safe_tb())

    # Persist bootstrap context into SQLite (single runtime DB).
    cache = SqliteCacheService(store_id=STORE_ID)
    cache.set_config("store_id", STORE_ID)
    cache.set_config("ho_url", ho_url)
    cache.set_config("tenant_id", runtime_config.get("tenant_id"))

    # Keep store_agent.db trimmed + VACUUMed on a timer so it never bloats.
    from store_agent.services.maintenance_service import start_cache_maintenance_thread
    start_cache_maintenance_thread(cache.db_path, log=_log)

    threading.Thread(
        target=_heartbeat_loop,
        args=(runtime_config.get("connection_type"), cache),
        daemon=True,
    ).start()

    # Phase 028C: discover schema and upload catalog delta once at startup.
    try:
        discovery_conn = RuntimeSqlConnectionService().connect(runtime_context)
        delta = CatalogDeltaService(discovery_conn, cache, config.active_ho_url(), STORE_ID).run()
        _log("[CATALOG] delta: " + str(delta))
        discovery_conn.close()
    except Exception:
        _log("[CATALOG] discovery failed:\n" + _safe_tb())

    # FILE_TRANSFER mode (objective 5/6): mutually exclusive with the
    # DIRECT_HTTP loop below -- a store runs exactly one sync engine, never
    # both, so there is never more than one active sync per store. Default
    # (file_transfer.enabled absent/false) is untouched: every existing
    # DIRECT_HTTP deployment behaves exactly as before this change.
    ft_cfg = file_transfer_config.file_transfer_config()
    if ft_cfg["enabled"]:
        _log("[AGENT] FILE_TRANSFER mode enabled (interval=%ss)" % ft_cfg["interval_seconds"])
        while True:
            if _license_locked(cache):
                _log("[FILE_TRANSFER] skipped: license " + str(cache.get_config("license_state")))
                time.sleep(ft_cfg["interval_seconds"])
                continue
            new_runtime_config = _refresh_runtime_config(runtime_config, config.active_ho_url())
            if new_runtime_config is not runtime_config:
                runtime_config = new_runtime_config
                runtime_context = RuntimeContextFactory().create(runtime_config)
            _run_file_transfer_cycle(runtime_context, runtime_config, cache)
            time.sleep(ft_cfg["interval_seconds"])

    # Sync loop is fully self-contained: any failure (chunk upload, schema
    # evolution, merge, connection) is caught and logged, the connection is
    # always released, and the loop keeps polling. It can never break, and it
    # never touches the heartbeat thread above. It re-resolves the HO URL each
    # cycle so it follows the same route the heartbeat settled on.
    while True:
        if _license_locked(cache):
            _log("[SYNC] skipped: license " + str(cache.get_config("license_state")))
            time.sleep(SYNC_POLL_SECONDS)
            continue
        connection = None
        try:
            new_runtime_config = _refresh_runtime_config(runtime_config, config.active_ho_url())
            if new_runtime_config is not runtime_config:
                runtime_config = new_runtime_config
                runtime_context = RuntimeContextFactory().create(runtime_config)
            connection = RuntimeSqlConnectionService().connect(runtime_context)
            orchestrator = SyncRuntimeOrchestrator(
                connection=connection,
                ho_api_url=config.active_ho_url(),
                store_id=STORE_ID,
            )
            result = orchestrator.run_cycle()
            if result["tasks_processed"]:
                _log("[SYNC] cycle: " + str(result))
        except Exception:
            _log("[SYNC] cycle failed:\n" + _safe_tb())
            config.mark_ho_failure()  # a network failure may mean this route is down
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        time.sleep(SYNC_POLL_SECONDS)


if __name__ == "__main__":
    main()
