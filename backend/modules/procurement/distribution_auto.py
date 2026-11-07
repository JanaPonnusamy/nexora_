"""Background internal-supplier-stock distribution for agent-synced sources.

A warehouse store (e.g. SHP for the SMS tenant, like NMW for the Nathan
tenant) should keep feeding its own live stock into the other stores'
procurement.supplier_stock automatically -- not only when someone presses
'Update Supplier Stock Only' on the Distribution screen. This loop calls the
existing distribution_service.generate(..., supplier_update_only=True) on a
timer for each configured tenant/source-store pair, using the 'nexora'
provider (reads sync.Products -- correct for an agent-synced warehouse; a
LAN-connected warehouse like NMW keeps using the manual/legacy path).

Config (env):
  DISTRIBUTION_AUTO_SOURCES  comma-separated "tenant_id:source_store_code"
                             pairs, e.g. "2D5ED813-...:SHP"; unset = off
  DISTRIBUTION_AUTO_MINUTES  interval, default 15 (minimum 5)
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def configured_sources():
    pairs = []
    for raw in os.getenv("DISTRIBUTION_AUTO_SOURCES", "").split(","):
        raw = raw.strip()
        if not raw or ":" not in raw:
            continue
        tenant_id, source_store_code = raw.split(":", 1)
        tenant_id, source_store_code = tenant_id.strip(), source_store_code.strip()
        if tenant_id and source_store_code:
            pairs.append((tenant_id, source_store_code))
    return pairs


def interval_seconds():
    try:
        minutes = int(os.getenv("DISTRIBUTION_AUTO_MINUTES", "15"))
    except ValueError:
        minutes = 15
    return max(5, minutes) * 60


def run_once(sources=None):
    """Run one stock-only distribution pass per configured source; a
    source's failure is logged and skipped, never blocks the others."""
    from modules.procurement import distribution_service

    results = {}
    for tenant_id, source_store_code in (sources if sources is not None else configured_sources()):
        key = f"{tenant_id}:{source_store_code}"
        try:
            results[key] = distribution_service.generate(
                tenant_id, source_store_code, "nexora",
                supplier_update_only=True, started_by="auto",
            )
        except Exception as exc:
            logger.info("[DISTRIBUTION_AUTO] %s skipped: %s", key, exc)
            results[key] = None
    return results


def _loop():
    # Let the backend finish starting (DB pools, other startup hooks) first.
    time.sleep(60)
    while True:
        try:
            result = run_once()
            logger.info("[DISTRIBUTION_AUTO] ran %s", result)
        except Exception:
            logger.exception("[DISTRIBUTION_AUTO] run failed")
        time.sleep(interval_seconds())


def start_background_loop():
    global _started
    if not configured_sources():
        return False
    with _lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_loop, name="distribution-auto", daemon=True).start()
    print(f"[DISTRIBUTION_AUTO] every {interval_seconds() // 60} min for {configured_sources()}")
    return True
