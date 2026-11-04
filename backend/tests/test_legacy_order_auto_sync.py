"""Background platform -> OrderNMC sync (legacy_order.auto_sync)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.legacy_order import auto_sync, service  # noqa: E402


def test_disabled_without_store_list(monkeypatch):
    monkeypatch.delenv("LEGACY_AUTO_SYNC_STORES", raising=False)
    assert auto_sync.configured_stores() == []
    assert auto_sync.start_background_loop() is False


def test_interval_has_a_floor(monkeypatch):
    monkeypatch.setenv("LEGACY_AUTO_SYNC_MINUTES", "1")
    assert auto_sync.interval_seconds() == 300
    monkeypatch.setenv("LEGACY_AUTO_SYNC_MINUTES", "bad")
    assert auto_sync.interval_seconds() == 900


def test_run_once_skips_live_device_sync_and_busy_stores(monkeypatch):
    calls = []

    def fake_start_sync(store, tables=None, live_device_sync=True):
        calls.append((store, live_device_sync))
        if store == "SMF":
            raise ValueError("A order job is already running for 'SMF'.")
        return "job-" + store

    monkeypatch.setattr(service, "start_sync", fake_start_sync)
    assert auto_sync.run_once(["SMG", "SMF"]) == {"SMG": "job-SMG", "SMF": None}
    assert calls == [("SMG", False), ("SMF", False)]


def test_platform_sync_only_asks_device_when_live(monkeypatch):
    asked = []
    monkeypatch.setattr(service.device_sync, "trigger_and_wait",
                        lambda *a, **k: asked.append(a[1]))
    monkeypatch.setattr(service.database, "central_connection_string", lambda: "dest")
    monkeypatch.setattr(service.database, "platform_connection_string", lambda: "src")
    monkeypatch.setattr(service.sync_engine, "sync_table", lambda *a, **k: (0, []))
    monkeypatch.setattr(service.repository, "mark_sync_result", lambda *a: None)
    monkeypatch.setattr(service, "_update", lambda *a, **k: None)
    store = {"store_name": "SMG"}
    plan = [("Products", "Products")]
    service._run_platform_sync("j", store, "sid", plan, live_device_sync=False)
    assert asked == []
    service._run_platform_sync("j", store, "sid", plan)
    assert asked == ["SMG"]
