"""DB-free tests for the Order Process checkpoint: the operator's last bill /
last GRN must be in OrderNMC after the pre-order sync, or no order is made."""

import contextlib
import datetime
import os
import sys
from types import SimpleNamespace

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.legacy_order import repository, service  # noqa: E402


@pytest.mark.parametrize("bill, grn, expected", [
    (None, None, (None, None)),
    ("  c01042645 ", " 2742 ", ("C01042645", 2742)),
    ("42645", 2742, ("42645", 2742)),
    ("", "", (None, None)),
    ("C01042645", None, ("C01042645", None)),
])
def test_normalize_checkpoint(bill, grn, expected):
    assert repository.normalize_checkpoint(bill, grn) == expected


@pytest.mark.parametrize("bill, grn", [("C1", "GRN-12"), ("C1", "-5"), ("X" * 51, None), (None, "1234567890")])
def test_normalize_checkpoint_rejects_garbage(bill, grn):
    with pytest.raises(ValueError):
        repository.normalize_checkpoint(bill, grn)


class _FakeCursor:
    """Answers the four checkpoint queries from canned rows."""

    def __init__(self, bill_row, latest_bill, grn_row, latest_grn):
        self.rows = {"bill": bill_row, "latest_bill": latest_bill, "grn": grn_row, "latest_grn": latest_grn}
        self.params = []
        self._next = None

    def execute(self, sql, *params):
        self.params.append(params)
        if "FROM SaleInformation" in sql:
            self._next = self.rows["bill" if "BNumber = ?" in sql else "latest_bill"]
        else:
            self._next = self.rows["grn" if "Grnnumber = ?" in sql else "latest_grn"]
        return self

    def fetchone(self):
        return self._next


def _patch_db(monkeypatch, cursor):
    @contextlib.contextmanager
    def conn():
        yield SimpleNamespace(cursor=lambda: cursor)
    monkeypatch.setattr(repository.database, "get_central_connection", conn)


T = datetime.datetime(2026, 11, 4, 16, 38)


def test_check_finds_bill_by_series_number_and_grn(monkeypatch):
    cur = _FakeCursor(SimpleNamespace(BNumber="C01042645", BillAt=T),
                      SimpleNamespace(BNumber="C01042645", BillAt=T),
                      SimpleNamespace(Grnnumber=2742, grndate=T, InvoiceSeries="IV  "),
                      SimpleNamespace(Grnnumber=2742, grndate=T))
    _patch_db(monkeypatch, cur)
    check = repository.check_order_checkpoint("SMG", "42645", 2742)
    assert check["ok"] is True
    assert check["bill"]["matched"] == "C01042645" and check["grn"]["series"] == "IV"
    # Store-scoped, and the digits are also tried as the series number.
    assert cur.params[0][0] == "SMG" and cur.params[0][2:] == ("42645", 42645)
    assert "C01042645" in check["message"] and "2742" in check["message"]


def test_check_reports_the_latest_synced_values_on_a_miss(monkeypatch):
    _patch_db(monkeypatch, _FakeCursor(None, SimpleNamespace(BNumber="C01042640", BillAt=T),
                                       None, SimpleNamespace(Grnnumber=2741, grndate=T)))
    check = repository.check_order_checkpoint("SMG", "C01042645", 2742)
    assert check["ok"] is False
    assert "C01042640" in check["message"] and "2741" in check["message"]
    assert check["message"][0].isupper()


def test_check_skips_the_part_that_was_not_entered(monkeypatch):
    _patch_db(monkeypatch, _FakeCursor(None, None, SimpleNamespace(Grnnumber=9, grndate=T, InvoiceSeries="IV"), None))
    check = repository.check_order_checkpoint("NMC", None, 9)
    assert check["ok"] is True and check["bill"] is None


def test_gate_passes_without_db_when_nothing_entered(monkeypatch):
    monkeypatch.setattr(service.repository, "check_order_checkpoint",
                        lambda *a: pytest.fail("no check when nothing was entered"))
    assert service._check_checkpoint("j", "NMC", (None, None)) == (True, None)
    assert service._check_checkpoint("j", "NMC", None) == (True, None)


def test_gate_treats_a_failed_check_as_a_miss(monkeypatch):
    monkeypatch.setattr(service, "_update", lambda job_id, **f: None)

    def boom(*a):
        raise RuntimeError("OrderNMC down")
    monkeypatch.setattr(service.repository, "check_order_checkpoint", boom)
    ok, check = service._check_checkpoint("j", "NMC", ("C1", None))
    assert ok is False and "OrderNMC down" in check["message"]


def _agent_run(monkeypatch, check_ok):
    updates, pushed = [], []
    monkeypatch.setattr(service, "_update", lambda job_id, **f: updates.append(f))
    monkeypatch.setattr(service, "_run_platform_sync", lambda *a, **k: ([{"table": "SaleInformation", "rows": 3}], []))
    monkeypatch.setattr(service.repository, "stale_sale_bill_warning", lambda store: None)
    monkeypatch.setattr(service.repository, "check_order_checkpoint",
                        lambda store, bill, grn: {"ok": check_ok, "message": "checked", "bill": None, "grn": None})
    monkeypatch.setattr(service, "_push_to_mirrors", lambda store, job_id=None: pushed.append((store, job_id)))
    ran = []

    def run_order(*a, **k):
        ran.append(a[0]["store_name"])
        return {"rows": 525}
    monkeypatch.setattr(service.order_process, "run_order_process", run_order)
    service._run_agent_sync_then_order("j1", {"store_name": "SMF"}, "sid", [("SaleInformation", "SaleInformation")],
                                       15, 20, "local", checkpoint=("C9", 5))
    return updates, ran, pushed


def test_agent_order_not_generated_when_checkpoint_missing(monkeypatch):
    updates, ran, pushed = _agent_run(monkeypatch, check_ok=False)
    assert ran == [] and pushed == []
    final = updates[-1]
    assert final["status"] == "failed" and final["error"] == "checked"
    assert final["result"]["checkpoint"]["ok"] is False


def test_agent_order_generated_and_pushed_when_checkpoint_found(monkeypatch):
    updates, ran, pushed = _agent_run(monkeypatch, check_ok=True)
    assert ran == ["SMF"] and pushed == [("SMF", "j1")]
    final = [u for u in updates if u.get("status") == "completed"][-1]
    assert final["result"]["checkpoint"]["ok"] is True and final["result"]["rows"] == 525
