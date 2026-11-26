"""Warehouse-stock refresh forcing a live device sync for an agent-synced
source (any tenant's warehouse -- e.g. SHP under SMS, NMW if ever agent-
synced -- never hardcoded to one store name)."""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.legacy_order import order_process  # noqa: E402


def test_agent_source_triggers_live_sync_when_stale(monkeypatch):
    asked = []
    synced_tables = []
    monkeypatch.setattr(order_process.device_sync, "trigger_and_wait",
                         lambda store_id, store_name, **k: asked.append((store_id, store_name)))
    monkeypatch.setattr(order_process.database, "platform_store_id", lambda name: "SID-" + name)
    monkeypatch.setattr(order_process.database, "central_connection_string", lambda: "dest")
    monkeypatch.setattr(order_process.database, "platform_connection_string", lambda: "src")
    monkeypatch.setattr(order_process.sync_engine, "sync_table",
                         lambda *a, **k: (synced_tables.append(a[2]), (0, []))[1])

    source_store = {"store_name": "SHP", "connection_type": "AGENT", "last_sync_time": None}
    order_process._sync_agent_source_stock(source_store)

    assert asked == [("SID-SHP", "SHP")]
    assert synced_tables == ["Products", "PurchaseTrans", "Batches"]


def test_agent_source_skipped_when_recently_synced(monkeypatch):
    asked = []
    monkeypatch.setattr(order_process.device_sync, "trigger_and_wait",
                         lambda *a, **k: asked.append(a))
    monkeypatch.setenv("LEGACY_WAREHOUSE_STOCK_SYNC_MIN_INTERVAL_SECONDS", "900")

    source_store = {
        "store_name": "NMW",
        "connection_type": "AGENT",
        "last_sync_time": datetime.datetime.now() - datetime.timedelta(seconds=30),
    }
    order_process._sync_agent_source_stock(source_store)

    assert asked == []


def test_agent_source_not_hardcoded_to_one_store_name(monkeypatch):
    """Any store name with connection_type AGENT goes through the live-sync
    path -- this is a generic seam, not a check for a specific string."""
    asked = []
    monkeypatch.setattr(order_process.device_sync, "trigger_and_wait",
                         lambda store_id, store_name, **k: asked.append(store_name))
    monkeypatch.setattr(order_process.database, "platform_store_id", lambda name: "SID-" + name)
    monkeypatch.setattr(order_process.database, "central_connection_string", lambda: "dest")
    monkeypatch.setattr(order_process.database, "platform_connection_string", lambda: "src")
    monkeypatch.setattr(order_process.sync_engine, "sync_table", lambda *a, **k: (0, []))

    for name in ("SHP", "MWH", "NMW", "SOME_FUTURE_WAREHOUSE"):
        order_process._sync_agent_source_stock(
            {"store_name": name, "connection_type": "AGENT", "last_sync_time": None}
        )

    assert asked == ["SHP", "MWH", "NMW", "SOME_FUTURE_WAREHOUSE"]


def test_agent_source_without_platform_store_id_skips_quietly(monkeypatch):
    asked = []
    monkeypatch.setattr(order_process.device_sync, "trigger_and_wait",
                         lambda *a, **k: asked.append(a))
    monkeypatch.setattr(order_process.database, "platform_store_id", lambda name: None)

    order_process._sync_agent_source_stock(
        {"store_name": "SHP", "connection_type": "AGENT", "last_sync_time": None}
    )

    assert asked == []


def test_agent_source_sync_failure_does_not_raise(monkeypatch):
    def boom(*a, **k):
        raise order_process.device_sync.DeviceSyncTimeout("offline")

    monkeypatch.setattr(order_process.device_sync, "trigger_and_wait", boom)
    monkeypatch.setattr(order_process.database, "platform_store_id", lambda name: "SID-SHP")

    # Must not raise -- the caller (refresh_warehouse_stock -> run_order_process)
    # relies on this being best-effort so a stale/offline warehouse device
    # never blocks retail order generation.
    order_process._sync_agent_source_stock(
        {"store_name": "SHP", "connection_type": "AGENT", "last_sync_time": None}
    )


def test_refresh_warehouse_stock_syncs_agent_source_before_reading(monkeypatch):
    calls = []
    monkeypatch.setattr(order_process.repository, "get_store",
                         lambda name: {"store_name": name, "connection_type": "AGENT",
                                       "last_sync_time": None})
    monkeypatch.setattr(order_process, "_sync_agent_source_stock",
                         lambda source_store, on_progress=None: calls.append("synced"))
    def fake_central_branch_stock(name):
        calls.append("read_central")
        return []

    monkeypatch.setattr(order_process.repository, "central_branch_stock", fake_central_branch_stock)
    monkeypatch.setattr(order_process.repository, "replace_supplier_stock",
                         lambda *a, **k: 0)
    monkeypatch.setattr(order_process.repository, "sync_supplier_product_match_from_mapping",
                         lambda *a, **k: 0)

    store = {"store_name": "SMG", "ho_code": "SHP"}
    order_process.refresh_warehouse_stock(store, "SHP")

    assert calls[0] == "synced"  # live sync happens BEFORE reading central_branch_stock


def test_refresh_warehouse_stock_leaves_non_agent_source_untouched(monkeypatch):
    """LAN/branch-connected sources are already fresh (direct branch pull) --
    this seam must never be invoked for them."""
    called = []
    monkeypatch.setattr(order_process.repository, "get_store",
                         lambda name: {"store_name": name, "connection_type": "LAN",
                                       "server_name": "s", "database": "d",
                                       "username": "u", "password": "p"})
    monkeypatch.setattr(order_process, "_sync_agent_source_stock",
                         lambda *a, **k: called.append("synced"))
    monkeypatch.setattr(order_process.repository, "branch_stock", lambda source: [])
    monkeypatch.setattr(order_process.repository, "replace_supplier_stock",
                         lambda *a, **k: 0)
    monkeypatch.setattr(order_process.repository, "sync_supplier_product_match_from_mapping",
                         lambda *a, **k: 0)

    store = {"store_name": "NMA", "ho_code": "NMW"}
    order_process.refresh_warehouse_stock(store, "NMW")

    assert called == []
