"""Morning auto-repair ladder: restart / update / reinstall, once each a day."""
import datetime

import pytest

from modules.legacy_order import morning_repair as mr

DEVICE = {"device_id": "d1", "online": True}


@pytest.fixture
def env(monkeypatch):
    calls = []
    state = {"alive": True, "agent": {"app_key": "store_agent", "installed": True, "version": "1.0.5", "status": "running"}}
    mr._state.clear()
    monkeypatch.setattr(mr, "_key", lambda store: (datetime.date.today(), "DB", store.upper()))
    monkeypatch.setattr(mr, "_online_device", lambda store: (DEVICE, state["agent"], None))
    monkeypatch.setattr(mr, "_agent_alive", lambda store: state["alive"])
    monkeypatch.setattr(mr, "target_agent_version", lambda: "1.0.7")
    monkeypatch.setattr(mr, "_wait_alive", lambda store: True)
    monkeypatch.setattr(mr, "_run", lambda device, action, version=None: calls.append((action, version)) or (True, f"{action} SUCCEEDED"))
    return calls, state


def test_live_heartbeat_restarts_first_then_reinstalls(env):
    calls, _ = env
    assert mr.repair("SMG", "sync failed")[0] and calls == [("restart", None)]
    calls.clear()
    ok, note = mr.repair("SMG", "sync failed")
    assert ok and calls[0] == ("update", "1.0.7") and "reinstalled" in note
    assert mr.repair("SMG", "sync failed") == (False, None)  # nothing left today


def test_dead_agent_on_old_version_is_updated(env):
    calls, state = env
    state["alive"] = False
    ok, note = mr.repair("SMA", "no agent heartbeat")
    assert ok and calls == [("update", "1.0.7"), ("start", None)] and "updated 1.0.5 -> 1.0.7" in note


def test_prepare_updates_once_and_never_downgrades(env):
    calls, state = env
    assert "1.0.5 -> 1.0.7" in mr.prepare("SMF")
    assert mr.prepare("SMF") is None and len(calls) == 1
    mr._state.clear()
    calls.clear()
    state["agent"] = {**state["agent"], "version": "1.0.9"}
    assert mr.prepare("SMF") is None and calls == []
