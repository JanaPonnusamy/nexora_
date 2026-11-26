"""Morning auto order: today's-bill gate and the per-store retry/give-up."""
import datetime

from modules.legacy_order import morning_order, repository, service


def test_today_bill_checkpoint_uses_the_today_check(monkeypatch):
    monkeypatch.setattr(service, "_update", lambda job_id, **f: None)
    monkeypatch.setattr(repository, "check_today_bill",
                        lambda store: {"ok": False, "message": "No sale bill from today", "bill": None, "grn": None})
    ok, check = service._check_checkpoint("j", "SMA", (repository.TODAY_BILL, None))
    assert ok is False and "today" in check["message"]


def _settings():
    return {"retry_minutes": 10, "until": "13:00"}


def test_no_bill_today_retries_inside_the_window(monkeypatch):
    marks = []
    monkeypatch.setattr(service, "start_order_process", lambda *a, **k: "job1")
    monkeypatch.setattr(morning_order, "_wait_for_job", lambda job_id: {
        "status": "failed", "result": {"checkpoint": {"ok": False, "message": "No sale bill from today yet."}}})
    monkeypatch.setattr(morning_order, "_mark", lambda store, day, status, msg, **k: marks.append((status, msg, k)))
    monkeypatch.setattr(morning_order, "_day_rows", lambda day: {"SMA": {"attempts": 1}})
    from modules.legacy_order import rulebook_order
    monkeypatch.setattr(rulebook_order, "get_order_mode", lambda store: None)
    morning_order.run_store("SMA", _settings(), datetime.datetime(2026, 11, 27, 8, 0))
    status, msg, extra = marks[-1]
    assert status == morning_order.WAITING and "08:10" in msg and extra["retry_at"].hour == 8


def test_gives_up_after_the_last_start(monkeypatch):
    marks = []
    monkeypatch.setattr(service, "start_order_process", lambda *a, **k: "job1")
    monkeypatch.setattr(morning_order, "_wait_for_job", lambda job_id: {"status": "failed", "error": "device offline"})
    monkeypatch.setattr(morning_order, "_mark", lambda store, day, status, msg, **k: marks.append((status, msg)))
    monkeypatch.setattr(morning_order, "_day_rows", lambda day: {"SMA": {"attempts": 5}})
    from modules.legacy_order import rulebook_order
    monkeypatch.setattr(rulebook_order, "get_order_mode", lambda store: None)
    morning_order.run_store("SMA", _settings(), datetime.datetime(2026, 11, 27, 12, 55))
    assert marks[-1][0] == morning_order.FAILED and "Gave up" in marks[-1][1]


def test_done_pushes_the_warehouse_stock(monkeypatch):
    marks, pushed = [], []
    from modules.legacy_order import order_process, rulebook_order
    monkeypatch.setattr(service, "start_order_process", lambda *a, **k: "job1")
    monkeypatch.setattr(morning_order, "_wait_for_job", lambda job_id: {"status": "completed", "result": {"rows": 412}})
    monkeypatch.setattr(morning_order, "_mark", lambda store, day, status, msg, **k: marks.append((status, msg)))
    monkeypatch.setattr(rulebook_order, "get_order_mode", lambda store: None)
    monkeypatch.setattr(service, "_resolve_store", lambda name: {"store_name": name, "ho_code": "SHP1", "tenant_id": "X"})
    monkeypatch.setattr(service, "is_warehouse_store", lambda name: False)
    monkeypatch.setattr(order_process, "_warehouse_stock_source_for", lambda store: "SHP")
    monkeypatch.setattr(order_process, "refresh_warehouse_stock", lambda store, src: pushed.append(src) or (206, 0))
    morning_order.run_store("SMA", _settings(), datetime.datetime(2026, 11, 27, 8, 0))
    assert pushed == ["SHP"] and marks[-1][0] == morning_order.DONE and "SHP stock pushed (206 rows)" in marks[-1][1]


import pytest

from modules.legacy_order import morning_repair


@pytest.fixture(autouse=True)
def _no_controller(monkeypatch):
    """No Device Controller in unit tests: nothing to prepare or repair."""
    monkeypatch.setattr(morning_repair, "prepare", lambda store, progress=None: None)
    monkeypatch.setattr(morning_repair, "repair", lambda store, reason, progress=None: (False, None))


def test_sync_failure_auto_repairs_then_retries_in_a_minute(monkeypatch):
    marks, repairs = [], []
    from modules.legacy_order import rulebook_order
    monkeypatch.setattr(service, "start_order_process", lambda *a, **k: "job1")
    monkeypatch.setattr(morning_order, "_wait_for_job", lambda job_id: {
        "status": "failed", "error": "agent offline",
        "message": "Live device sync did not complete. Order generation was not started: agent offline"})
    monkeypatch.setattr(morning_order, "_mark", lambda store, day, status, msg, **k: marks.append((status, msg, k)))
    monkeypatch.setattr(morning_order, "_day_rows", lambda day: {"SMG": {"attempts": 1}})
    monkeypatch.setattr(rulebook_order, "get_order_mode", lambda store: None)
    monkeypatch.setattr(morning_repair, "repair",
                        lambda store, reason, progress=None: repairs.append(store) or (True, "Auto-repair: Store Agent restarted, heartbeat back."))
    morning_order.run_store("SMG", _settings(), datetime.datetime(2026, 11, 27, 8, 0))
    status, msg, extra = marks[-1]
    assert repairs == ["SMG"] and status == morning_order.WAITING and "restarted" in msg
    assert (extra["retry_at"] - datetime.datetime.now()).total_seconds() < 120


def test_bill_missing_is_not_a_sync_failure(monkeypatch):
    repairs = []
    monkeypatch.setattr(morning_repair, "repair", lambda *a, **k: repairs.append(a) or (True, "x"))
    assert not morning_order._is_sync_failure({"message": "Order not generated: the last bill / last GRN was not found after sync."})
    assert morning_order._is_sync_failure({"message": "Platform sync failed. Order generation was not started."})


def test_store_order_and_weekdays(monkeypatch):
    monkeypatch.setattr(repository, "list_stores", lambda active: [{"store_name": n} for n in ("SMA", "SMF", "SMG", "SHP")])
    assert morning_order._target_stores(["smg", "SMA", "SMF", "SMG"]) == ["SMG", "SMA", "SMF"]
    assert morning_order._clean_days(None) == [0, 1, 2, 3, 4, 5]
    assert 6 not in morning_order._clean_days(None)  # no Sunday by default
    assert morning_order._clean_days([6, "2", "x", 9]) == [2, 6]


def test_sunday_is_skipped(monkeypatch):
    monkeypatch.setattr(morning_order, "tenants", lambda: [{"tenant_id": None, "tenant_name": None, "database": "OrderSMS"}])
    monkeypatch.setattr(morning_order, "_read_settings", lambda: {
        "enabled": True, "run_at": "07:45", "until": "09:00", "retry_minutes": 10, "stores": None, "days": [0, 1, 2, 3, 4, 5]})
    monkeypatch.setattr(morning_order, "_day_rows", lambda day: pytest.fail("Sunday must not be looked at"))
    assert morning_order.tick(datetime.datetime(2026, 11, 29, 8, 0)) is None  # a Sunday
