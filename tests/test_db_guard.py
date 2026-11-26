"""DB guard: safe auto-repair of broken databases + the maintenance status."""
from modules.legacy_order import database, db_guard


def _setup(monkeypatch, states, recover_ok=True):
    calls = []
    monkeypatch.setattr(db_guard, "watched_databases", lambda: [("NEXORA_PLATFORM", "platform"), ("OrderSMS", "legacy")])
    monkeypatch.setattr(db_guard, "_read_all", lambda names: states)
    monkeypatch.setattr(db_guard, "_auto_close_off", lambda name: calls.append(("auto_close", name)))
    monkeypatch.setattr(db_guard, "_alert", lambda name, msg: calls.append(("alert", name)))

    def recover(allow_data_loss=False, database=None):
        calls.append(("recover", database, allow_data_loss))
        return {"ok": recover_ok, "after": {"state": "ONLINE" if recover_ok else "SUSPECT", "access": "MULTI_USER"},
                "message": "Recovered" if recover_ok else "still SUSPECT"}
    monkeypatch.setattr(database, "recover_database", recover)
    return calls


def test_recovery_pending_is_repaired_without_data_loss(monkeypatch):
    calls = _setup(monkeypatch, {"NEXORA_PLATFORM": ("ONLINE", "MULTI_USER", False),
                                 "ORDERSMS": ("RECOVERY_PENDING", "MULTI_USER", False)})
    s = db_guard.check_once()
    assert ("recover", "OrderSMS", False) in calls
    assert all(d["ok"] for d in s["databases"]) and db_guard.status()["status"] == "ok"


def test_unfixable_platform_db_alerts_and_shows_maintenance(monkeypatch):
    calls = _setup(monkeypatch, {"NEXORA_PLATFORM": ("SUSPECT", "MULTI_USER", False),
                                 "ORDERSMS": ("ONLINE", "MULTI_USER", True)}, recover_ok=False)
    db_guard.check_once()
    assert ("alert", "NEXORA_PLATFORM") in calls and ("auto_close", "OrderSMS") in calls
    st = db_guard.status()
    assert st["maintenance"] and "NEXORA_PLATFORM" in st["message"]


def test_restore_in_progress_is_left_alone(monkeypatch):
    calls = _setup(monkeypatch, {"NEXORA_PLATFORM": ("ONLINE", "MULTI_USER", False),
                                 "ORDERSMS": ("RESTORING", "MULTI_USER", False)})
    db_guard.check_once()
    assert not any(c[0] == "recover" for c in calls)


def test_sql_down_is_maintenance(monkeypatch):
    def boom(names):
        raise RuntimeError("Login timeout expired")
    monkeypatch.setattr(db_guard, "watched_databases", lambda: [("NEXORA_PLATFORM", "platform")])
    monkeypatch.setattr(db_guard, "_read_all", boom)
    db_guard.check_once()
    st = db_guard.status()
    assert st["maintenance"] and st["reason"] == "database_unreachable"
