"""Background platform -> OrderNMC sync for agent-synced stores.

Agent stores (e.g. the SMS group's SMG/SMF on the .32 HO) deliver their POS
data to NEXORA_PLATFORM.sync.* on their own. Without this loop that data only
reaches OrderNMC when someone presses Sync or Order Process; with it, OrderNMC
(and so the OrderNMC mirror to the remote PC) stays at most one interval old.

Each run copies what is already in sync.* (no live device sync request -- the
manual Sync / Order Process still do that) using the legacy sync engine's
incremental watermarks + MERGE, so a quiet run is cheap.

Config (env):
  LEGACY_AUTO_SYNC_STORES   comma-separated OrderNMC StoreNames; unset = off
  LEGACY_AUTO_SYNC_MINUTES  interval, default 15 (minimum 5)
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def configured_stores():
    return [s.strip() for s in os.getenv("LEGACY_AUTO_SYNC_STORES", "").split(",") if s.strip()]


def interval_seconds():
    try:
        minutes = int(os.getenv("LEGACY_AUTO_SYNC_MINUTES", "15"))
    except ValueError:
        minutes = 15
    return max(5, minutes) * 60


def run_once(stores=None):
    """Start one background sync per store; a store whose previous job (or a
    manual Sync / Order Process) is still running is skipped this round."""
    from modules.legacy_order import service

    started = {}
    for store in stores if stores is not None else configured_stores():
        try:
            started[store] = service.start_sync(store, live_device_sync=False)
        except Exception as exc:  # running job, unknown store, DB down ...
            logger.info("[LEGACY_AUTO_SYNC] %s skipped: %s", store, exc)
            started[store] = None
    return started


def _loop():
    # Let the backend finish starting (DB pools, other startup hooks) first.
    time.sleep(60)
    while True:
        try:
            result = run_once()
            logger.info("[LEGACY_AUTO_SYNC] started %s", result)
        except Exception:
            logger.exception("[LEGACY_AUTO_SYNC] run failed")
        time.sleep(interval_seconds())


def start_background_loop():
    global _started
    if not configured_stores():
        return False
    with _lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_loop, name="legacy-auto-sync", daemon=True).start()
    print(f"[LEGACY_AUTO_SYNC] every {interval_seconds() // 60} min for {configured_stores()}")
    return True
