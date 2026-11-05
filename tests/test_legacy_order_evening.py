"""DB-free tests for the evening (second) order schedule and the Order
Process "Compare today's previous order" hook."""

import datetime
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.legacy_order import evening_order, service  # noqa: E402

D = datetime.datetime


def test_parse_run_at_accepts_hh_mm_and_rejects_garbage():
    assert evening_order.parse_run_at("18:25") == datetime.time(18, 25)
    assert evening_order.parse_run_at(" 7:05 ") == datetime.time(7, 5)
    for bad in ("", "18", "25:00", "18:61", "six"):
        with pytest.raises(ValueError):
            evening_order.parse_run_at(bad)


@pytest.mark.parametrize("now, last_run, due", [
    (D(2026, 11, 4, 18, 24), None, False),                         # before start
    (D(2026, 11, 4, 18, 25), None, True),                          # at start
    (D(2026, 11, 4, 20, 0), datetime.date(2026, 11, 3), True),     # backend was down: catch up
    (D(2026, 11, 4, 21, 26), None, False),                         # past the catch-up window
    (D(2026, 11, 4, 18, 30), datetime.date(2026, 11, 4), False),   # already ran today
])
def test_is_due(now, last_run, due):
    assert evening_order.is_due(now, "18:25", last_run, 180) is due


def test_next_run():
    today = datetime.date(2026, 11, 4)
    assert evening_order.next_run(D(2026, 11, 4, 9, 0), False, "18:25", None, 180) is None
    assert evening_order.next_run(D(2026, 11, 4, 9, 0), True, "18:25", None, 180) == D(2026, 11, 4, 18, 25)
    assert evening_order.next_run(D(2026, 11, 4, 19, 0), True, "18:25", today, 180) == D(2026, 11, 5, 18, 25)


def test_target_stores_all_or_configured(monkeypatch):
    monkeypatch.setattr(evening_order.repository, "list_stores",
                        lambda active_only: [{"store_name": n} for n in ("NMW", "NMS", "NMC", "NMV")])
    assert evening_order.target_stores(None) == ["NMW", "NMS", "NMC", "NMV"]
    assert evening_order.target_stores(["nmc", "NMS", "GONE"]) == ["NMS", "NMC"]


def test_run_stores_runs_one_at_a_time_with_compare_and_warnings_acknowledged(monkeypatch):
    calls, saved = [], []

    def start(name, **kwargs):
        calls.append((name, kwargs))
        if name == "NMV":
            raise ValueError("A sync job is already running for 'NMV'.")
        return f"job-{name}"

    jobs = {"job-NMS": {"status": "completed", "result": {"rows": 10, "compare": {"order_id": 7, "affected_rows": 3}}},
            "job-NMC": {"status": "failed", "result": None, "error": "sync failed"}}
    monkeypatch.setattr(service, "start_order_process", start)
    monkeypatch.setattr(evening_order, "_wait_for_job", lambda job_id: jobs[job_id])
    monkeypatch.setattr(evening_order, "_save_summary", lambda summary, finished: saved.append(finished))

    summary = evening_order.run_stores(["NMS", "NMC", "NMV"], "schedule")

    assert [c[0] for c in calls] == ["NMS", "NMC", "NMV"]
    assert all(c[1] == {"confirmed_stale_order": True} for c in calls)
    by_store = {e["store_name"]: e for e in summary["stores"]}
    assert by_store["NMS"]["status"] == "completed" and by_store["NMS"]["compare"]["affected_rows"] == 3
    assert by_store["NMC"]["status"] == "failed" and by_store["NMC"]["error"] == "sync failed"
    assert by_store["NMV"]["status"] == "skipped"
    assert saved[-1] is True and summary["finished_at"]


def test_compare_hook_skips_without_an_earlier_order_today(monkeypatch):
    messages = []
    monkeypatch.setattr(service, "_update", lambda job_id, **f: messages.append(f.get("message")))
    monkeypatch.setattr(service.repository, "todays_previous_order_ids", lambda store: [])
    # ...and no previous active day either (the day's first order compares with it).
    monkeypatch.setattr(service.repository, "previous_active_day_order_ids", lambda store: [])
    monkeypatch.setattr(service.repository, "compare_previous_order",
                        lambda *a: pytest.fail("nothing to compare with"))
    assert service._compare_todays_previous("j", "NMC") == {"order_id": None, "order_ids": [], "affected_rows": 0}
    assert "no earlier order" in messages[-1]


def test_compare_hook_compares_and_never_raises(monkeypatch):
    messages = []
    monkeypatch.setattr(service, "_update", lambda job_id, **f: messages.append(f.get("message")))
    calls = []
    monkeypatch.setattr(service.repository, "todays_previous_order_ids", lambda store: [2026110401, 2026110402])

    def compare(store, order_id):
        calls.append(order_id)
        return {"store_name": store, "order_id": order_id, "affected_rows": 21}
    monkeypatch.setattr(service.repository, "compare_previous_order", compare)
    result = service._compare_todays_previous("j", "NMC")
    # Every earlier order today, oldest first (the newest decision wins).
    assert calls == [2026110401, 2026110402]
    assert result["affected_rows"] == 42 and result["order_id"] == 2026110402
    assert "2026110401, 2026110402" in messages[-1]

    def boom(*a):
        raise RuntimeError("deadlock")
    monkeypatch.setattr(service.repository, "compare_previous_order", boom)
    result = service._compare_todays_previous("j", "NMC")
    assert result["error"] == "deadlock" and "failed" in messages[-1]
