"""Tests for the NMV integration seam in Legacy Order.

Verifies that an agent-synced store (NMV) reads its order-generation supporting
data from the central OrderNMC copy (StoreName-scoped), while the five LAN
stores keep reading the branch database byte-for-byte. No live DB: a fake
connection records which connection string each query ran on.
"""
from __future__ import annotations

import datetime

import pytest

from modules.legacy_order import order_process, service

CENTRAL_CS = "CENTRAL_CS"
BRANCH_CS = "BRANCH_CS"


# --------------------------------------------------------------------------
# Fake DB plumbing for update_order_header_details
# --------------------------------------------------------------------------

class FakeRow:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self._vals = list(kw.values())

    def __getitem__(self, i):
        return self._vals[i]


class FakeCursor:
    def __init__(self, conn, calls):
        self.conn = conn
        self.calls = calls
        self._last = ""

    def execute(self, sql, *params):
        self.calls.append({"cs": self.conn.cs, "sql": sql, "params": params})
        self._last = sql
        return self

    def fetchone(self):
        s = self._last
        if "FROM ProductSaleInformation" in s:
            return FakeRow(Transactiondate=datetime.datetime(2026, 1, 2, 10, 0),
                           BNumber="C12345")
        if "FROM Purchasetrans" in s:
            return FakeRow(Grnnumber="GRN987")
        if "FROM OrderHeaderDetails" in s:        # COUNT(*)
            return FakeRow(n=0)
        if "FROM OrderManagement" in s:
            return FakeRow(WantedDate=datetime.datetime(2026, 1, 1),
                           OrderId=42, StoreName="NMV")
        return None

    def commit(self):
        pass


class FakeConn:
    def __init__(self, cs, calls):
        self.cs = cs
        self.calls = calls
        self.committed = 0

    def cursor(self):
        return FakeCursor(self, self.calls)

    def commit(self):
        self.committed += 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def header_env(monkeypatch):
    """Patch _connect + central_connection_string; return the shared call log."""
    calls = []

    def _connect(cs, timeout=30):
        return FakeConn(cs, calls)

    monkeypatch.setattr(order_process, "_connect", _connect)
    monkeypatch.setattr(order_process.database, "central_connection_string",
                        lambda: CENTRAL_CS)
    return calls


def _watermark_calls(calls):
    return [c for c in calls
            if "FROM ProductSaleInformation" in c["sql"] or "FROM Purchasetrans" in c["sql"]]


# --------------------------------------------------------------------------
# NMV (from_central=True): reads central, StoreName-scoped, never the branch
# --------------------------------------------------------------------------

def test_nmv_header_reads_central_store_scoped(header_env):
    calls = header_env
    result = order_process.update_order_header_details(
        "BRANCH_CS_MUST_NOT_BE_USED", "NMV", 13, 18, from_central=True
    )

    wm = _watermark_calls(calls)
    assert wm, "watermark reads should have run"
    # every watermark read ran on central, and the branch cs was never opened
    assert all(c["cs"] == CENTRAL_CS for c in wm)
    assert not any(c["cs"] == "BRANCH_CS_MUST_NOT_BE_USED" for c in calls)

    # both reads are StoreName-scoped to NMV (no cross-store leak possible)
    psi = next(c for c in calls if "FROM ProductSaleInformation" in c["sql"])
    assert "StoreName = ?" in psi["sql"]
    assert psi["params"] == ("NMV",)
    pt = next(c for c in calls if "FROM Purchasetrans" in c["sql"])
    assert "StoreName = ?" in pt["sql"]
    assert pt["params"] == ("NMV",)

    # last-sale + last-GRN captured correctly
    assert result["last_sale_bill_no"] == "C12345"
    assert result["last_grn"] == "GRN987"
    assert result["order_id"] == 42


def test_nmv_header_filters_prevent_other_store_leak(header_env):
    calls = header_env
    order_process.update_order_header_details(None, "NMV", 13, 18, from_central=True)
    # There is no central read of ProductSaleInformation / Purchasetrans that is
    # NOT scoped by StoreName -- a different store's rows cannot be selected.
    for c in _watermark_calls(calls):
        assert "WHERE StoreName = ?" in c["sql"]
        assert c["params"] == ("NMV",)


# --------------------------------------------------------------------------
# LAN (from_central=False): unchanged -- reads the branch, no StoreName filter
# --------------------------------------------------------------------------

def test_lan_header_reads_branch_unchanged(header_env):
    calls = header_env
    result = order_process.update_order_header_details(
        BRANCH_CS, "NMA", 13, 18, from_central=False
    )

    wm = _watermark_calls(calls)
    assert wm
    # watermark reads ran on the BRANCH connection...
    assert all(c["cs"] == BRANCH_CS for c in wm)
    # ...and the legacy branch queries carry NO StoreName filter (byte-for-byte)
    for c in wm:
        assert "StoreName" not in c["sql"]

    # the OrderManagement read + header insert still happen on central
    om = next(c for c in calls if "FROM OrderManagement" in c["sql"])
    assert om["cs"] == CENTRAL_CS
    assert result["last_sale_bill_no"] == "C12345"
    assert result["last_grn"] == "GRN987"


def test_lan_header_default_is_branch(header_env):
    """Omitting from_central (the LAN default) must read the branch."""
    calls = header_env
    order_process.update_order_header_details(BRANCH_CS, "NMC", 13, 18)
    assert all(c["cs"] == BRANCH_CS for c in _watermark_calls(calls))


# --------------------------------------------------------------------------
# run_order_process routing: agent-synced forces local + from_central
# --------------------------------------------------------------------------

@pytest.fixture
def process_env(monkeypatch):
    captured = {"header_kwargs": None}

    def fake_fetch(query_cs, odata, store_name, store_code, min_days, max_days,
                   mode, recency_days=10, sql_name=None):
        captured["query_cs"] = query_cs
        captured["mode"] = mode
        captured["sql_name"] = sql_name
        return (["ProductCode"], [])

    def fake_insert(columns, rows, store_name):
        return 0

    def fake_header(source_cs, store_name, min_days, max_days, from_central=False):
        captured["header_kwargs"] = {"source_cs": source_cs, "from_central": from_central}
        return None

    monkeypatch.setattr(order_process, "fetch_source_data", fake_fetch)
    monkeypatch.setattr(order_process, "insert_data_into_destination", fake_insert)
    monkeypatch.setattr(order_process, "update_order_header_details", fake_header)
    monkeypatch.setattr(order_process.database, "central_connection_string",
                        lambda: CENTRAL_CS)
    monkeypatch.setattr(order_process.database, "branch_connection_string",
                        lambda *a, **k: BRANCH_CS)
    return captured


_NMV_STORE = {"store_name": "NMV", "store_code": "9", "server_name": None,
              "database": None, "username": None, "password": None}
_NMA_STORE = {"store_name": "NMA", "store_code": "1", "server_name": "SRV",
              "database": "NMA_DB", "username": "u", "password": "p"}


def test_agent_synced_forces_local_and_central(process_env):
    # Even if the caller asked for remote, an agent-synced store must query the
    # central copy in local mode (there is no branch to reach).
    order_process.run_order_process(_NMV_STORE, 13, 18, "remote", is_agent_synced=True)
    assert process_env["query_cs"] == CENTRAL_CS
    assert process_env["mode"] == "local"
    assert process_env["header_kwargs"]["from_central"] is True


def test_lan_remote_still_uses_branch(process_env):
    order_process.run_order_process(_NMA_STORE, 13, 18, "remote")
    assert process_env["query_cs"] == BRANCH_CS
    assert process_env["header_kwargs"]["from_central"] is False


def test_lan_local_uses_central_but_branch_header(process_env):
    order_process.run_order_process(_NMA_STORE, 13, 18, "local")
    assert process_env["query_cs"] == CENTRAL_CS
    # LAN local still reads the header watermarks from the branch (unchanged)
    assert process_env["header_kwargs"]["from_central"] is False


# --------------------------------------------------------------------------
# Store classification + _resolve_store relaxation
# --------------------------------------------------------------------------

def test_lan_stores_are_not_agent_synced():
    for code in ("NMA", "NMW", "NMC", "NMG", "NMS"):
        assert service.is_agent_synced_store(code) is False
    assert service.is_agent_synced_store("NMV") is True
    assert service.is_agent_synced_store("nmv") is True  # case-insensitive


def test_resolve_store_allows_nmv_without_branch_db(monkeypatch):
    monkeypatch.setattr(service.repository, "get_store",
                        lambda sn: {"store_name": "NMV", "store_code": "9",
                                    "server_name": None, "database": None})
    # must NOT raise even though server/database are empty
    store = service._resolve_store("NMV")
    assert store["store_name"] == "NMV"


def test_resolve_store_still_requires_branch_db_for_lan(monkeypatch):
    monkeypatch.setattr(service.repository, "get_store",
                        lambda sn: {"store_name": "NMA", "store_code": "1",
                                    "server_name": None, "database": None})
    with pytest.raises(ValueError):
        service._resolve_store("NMA")


# --------------------------------------------------------------------------
# start_order_process routing: NMV skips branch sync/test, LAN keeps it
# --------------------------------------------------------------------------

class FakeThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

    def start(self):
        pass  # never actually run the worker in a test


@pytest.fixture
def thread_spy(monkeypatch):
    created = []

    def factory(*a, **k):
        t = FakeThread(*a, **k)
        created.append(t)
        return t

    monkeypatch.setattr(service.threading, "Thread", factory)
    return created


def test_start_order_process_nmv_syncs_from_platform(monkeypatch, thread_spy):
    monkeypatch.setattr(service, "_resolve_store", lambda sn: dict(_NMV_STORE))
    monkeypatch.setattr(service, "_running_job_kind", lambda sn: None)
    # NMV now resolves its platform store_id and syncs sync.* -> central first.
    monkeypatch.setattr(service.database, "platform_store_id",
                        lambda sc: "STORE-ID-GUID")

    branch_tested = {"called": False}

    def spy_test(store):
        branch_tested["called"] = True
        return True, None

    monkeypatch.setattr(service.repository, "test_branch_connection", spy_test)

    service.start_order_process("NMV")

    assert branch_tested["called"] is False  # no branch connection test for NMV
    t = thread_spy[-1]
    # NMV runs a platform->central sync and THEN generates the order
    assert t.target is service._run_agent_sync_then_order
    # the resolved platform store_id is threaded through to the worker
    assert "STORE-ID-GUID" in t.args


def test_start_order_process_lan_keeps_sync_then_order(monkeypatch, thread_spy):
    monkeypatch.setattr(service, "_resolve_store", lambda sn: dict(_NMA_STORE))
    monkeypatch.setattr(service, "_running_job_kind", lambda sn: None)

    branch_tested = {"called": False}

    def spy_test(store):
        branch_tested["called"] = True
        return True, None

    monkeypatch.setattr(service.repository, "test_branch_connection", spy_test)

    service.start_order_process("NMA")

    assert branch_tested["called"] is True  # LAN path still tests the branch
    t = thread_spy[-1]
    assert t.target is service._run_sync_then_order
