"""Tests for the Legacy Order "Final Business Requirements" additions:

  A. current-date-only pre-processing validation (repository.
     current_date_order / require_current_date_order_if_any, wired into
     service.start_order_process as StaleCurrentOrder)
  C. conditional backup audit signal for reviewed+assigned (QtyCheck=1,
     Status=1) rows (repository.record_protected_backup_snapshot, called
     from order_process.insert_data_into_destination)
  D. restore-by-OrderId (repository.restorable_order_preview /
     restore_backup_order, router endpoints, admin-gated)

Same layering convention as test_legacy_order_processing_lock.py: UNIT
(service, no SQL) / REPOSITORY (fake pyodbc-shaped connection, proves SQL
shape and control flow, not real SQL Server concurrency) / router-level
authorization tests (no DB needed).
"""
from __future__ import annotations

import datetime

import pytest
from fastapi import HTTPException

from modules.legacy_order import repository, router as lo_router, service


_NMA_STORE = {"store_name": "NMA", "store_code": "1", "server_name": "SRV",
              "database": "NMA_DB", "username": "u", "password": "p"}


# ===========================================================================
# A. current_date_order / require_current_date_order_if_any (REPOSITORY)
# ===========================================================================

class _DateFakeCursor:
    """Answers current_date_order's two queries: the MAX(OrderId)+today
    stamp row, and the WantedDate stamp row for that OrderId."""
    def __init__(self, latest_order_id, today_stamp, wanted_stamp):
        self.latest_order_id = latest_order_id
        self.today_stamp = today_stamp
        self.wanted_stamp = wanted_stamp
        self.last = ""

    def execute(self, sql, *params):
        self.last = sql.strip()
        return self

    def fetchone(self):
        if "MAX(OrderId)" in self.last:
            class Row:
                LatestOrderId = self.latest_order_id
                TodayStamp = self.today_stamp
            return Row()
        if "WantedDate" in self.last:
            class Row:
                WantedStamp = self.wanted_stamp
            return Row()
        return None


def test_current_date_order_accepts_matching_orderid_and_wanteddate():
    cur = _DateFakeCursor(20260101120000, "20260101", "20260101")
    assert repository.current_date_order(cur, "NMA") == 20260101120000


def test_current_date_order_rejects_no_order_at_all():
    cur = _DateFakeCursor(None, "20260101", None)
    with pytest.raises(repository.NoCurrentDateOrder, match="no order has been generated"):
        repository.current_date_order(cur, "NMA")


def test_current_date_order_rejects_stale_orderid_date():
    """Latest order's own OrderId timestamp is from yesterday -- never
    silently treated as today's, per the explicit "do not assume MAX(OrderId)
    means today's order" requirement."""
    cur = _DateFakeCursor(20251231235900, "20260101", "20251231")
    with pytest.raises(repository.NoCurrentDateOrder, match="not today"):
        repository.current_date_order(cur, "NMA")


def test_current_date_order_rejects_orderid_wanteddate_disagreement():
    """OrderId says today, but WantedDate disagrees -- an inconsistent row
    the function must refuse to treat as unambiguous, not silently pick one
    signal over the other."""
    cur = _DateFakeCursor(20260101120000, "20260101", "20251231")
    with pytest.raises(repository.NoCurrentDateOrder, match="disagree"):
        repository.current_date_order(cur, "NMA")


def test_require_current_date_order_if_any_returns_none_for_no_order(monkeypatch):
    class FakeCursor:
        def execute(self, sql, *params):
            return self

        def fetchone(self):
            return (None,)  # MAX(OrderId) is NULL

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(repository.database, "get_central_connection", lambda: FakeConn())

    # No order at all -> nothing to validate, must not raise.
    assert repository.require_current_date_order_if_any("NMA") is None


# ===========================================================================
# A. StaleCurrentOrder wired into service.start_order_process (UNIT)
# ===========================================================================

class FakeThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args

    def start(self):
        pass


@pytest.fixture
def thread_spy(monkeypatch):
    created = []

    def factory(*a, **k):
        t = FakeThread(*a, **k)
        created.append(t)
        return t

    monkeypatch.setattr(service.threading, "Thread", factory)
    return created


@pytest.fixture
def base_env(monkeypatch):
    monkeypatch.setattr(service, "_resolve_store", lambda sn: dict(_NMA_STORE))
    monkeypatch.setattr(service, "_running_job_kind", lambda sn: None)
    monkeypatch.setattr(service.repository, "test_branch_connection", lambda store: (True, None))
    # The durable processing-lock mechanism was removed; the only remaining
    # request-time gate is the current-date order check + QtyCheck warning.


def test_start_order_process_blocked_by_stale_current_order(base_env, thread_spy, monkeypatch):
    def raise_stale(sn):
        raise repository.NoCurrentDateOrder(sn, "the latest order (#1) was generated on 20260101, not today.")

    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", raise_stale)

    with pytest.raises(service.StaleCurrentOrder):
        service.start_order_process("NMA")

    assert not thread_spy, "no worker thread must start when the current-date order check fails"


def test_start_order_process_proceeds_when_order_is_current(base_env, thread_spy, monkeypatch):
    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", lambda sn: 20260101120000)
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (None, 0, []))

    job_id = service.start_order_process("NMA")

    assert job_id
    assert thread_spy


def test_start_order_process_proceeds_with_no_order_yet(base_env, thread_spy, monkeypatch):
    """A brand-new store with no order generated yet must not be blocked --
    only a genuinely STALE existing order is a problem."""
    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", lambda sn: None)
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (None, 0, []))

    job_id = service.start_order_process("NMA")

    assert job_id
    assert thread_spy


def test_start_order_process_confirmed_stale_order_skips_the_check(base_env, thread_spy, monkeypatch):
    """confirmed_stale_order=True is the Continue path on the stale-order
    warning dialog -- it must skip require_current_date_order_if_any
    entirely (not call it and ignore the result), same shape as how
    QtyCheckConfirmationRequired's `confirmed` skips its own re-raise."""
    def raise_if_called(sn):
        raise AssertionError("require_current_date_order_if_any must not be called when confirmed_stale_order=True")

    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", raise_if_called)
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (None, 0, []))

    job_id = service.start_order_process("NMA", confirmed_stale_order=True)

    assert job_id
    assert thread_spy


def test_start_order_process_agent_synced_store_skips_both_warnings(thread_spy, monkeypatch):
    """Agent-synced stores (NMV) have no operator directly working their
    grids between runs the way an on-LAN store does, so the owner asked to
    drop BOTH confirmation gates for them entirely (2026-10-23) -- neither
    require_current_date_order_if_any nor qty_check_confirmation_count
    should even be CALLED for this path, not just bypassed by a confirm
    flag, and the agent-sync job must start with no confirmed_* args at
    all."""
    nmv_store = {"store_name": "NMV", "store_code": "10", "server_name": "",
                 "database": "", "username": "", "password": ""}
    monkeypatch.setattr(service, "_resolve_store", lambda sn: dict(nmv_store))
    monkeypatch.setattr(service, "_running_job_kind", lambda sn: None)
    monkeypatch.setattr(service.database, "platform_store_id", lambda sn: "11111111-1111-1111-1111-111111111111")

    def raise_if_called(*a, **k):
        raise AssertionError("neither gate check must run for an agent-synced store")

    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", raise_if_called)
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", raise_if_called)

    job_id = service.start_order_process("NMV")

    assert job_id
    assert thread_spy
    assert thread_spy[0].target is service._run_agent_sync_then_order


def test_start_order_process_stale_confirm_does_not_bypass_qtycheck_warning(base_env, thread_spy, monkeypatch):
    """The two warnings are independent: confirming the stale-order dialog
    must NOT silently wave through the separate pending-supplier-assignment
    warning too -- the caller must still see and confirm that one on its
    own merits."""
    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", lambda sn: None)
    monkeypatch.setattr(
        service.repository, "qty_check_confirmation_count",
        lambda sn: (20260101120000, 3, [{"product_code": 1, "product_name": "X"}]),
    )

    with pytest.raises(service.QtyCheckConfirmationRequired):
        service.start_order_process("NMA", confirmed_stale_order=True)

    assert not thread_spy


# ===========================================================================
# C. record_protected_backup_snapshot (REPOSITORY)
# ===========================================================================

class _AuditFakeCursor:
    def __init__(self, protected_count):
        self.protected_count = protected_count
        self.calls = []
        self.last = ""

    def execute(self, sql, *params):
        self.last = sql.strip()
        self.calls.append((self.last, params))
        return self

    def fetchone(self):
        return (self.protected_count,)


def _audit_inserts(cur):
    """INSERT dbo.LegacyOrderWorkflowAudit calls -- action/old/new are bound
    params, not part of the SQL text (see repository._record_line_audit),
    so matching on the SQL string alone can't tell audit rows apart; filter
    by the target table instead and inspect the params for the action."""
    return [params for sql, params in cur.calls if "LegacyOrderWorkflowAudit" in sql]


def test_protected_snapshot_zero_rows_writes_no_audit():
    cur = _AuditFakeCursor(protected_count=0)
    count = repository.record_protected_backup_snapshot(cur, "NMA", 42)
    assert count == 0
    assert _audit_inserts(cur) == []


def test_protected_snapshot_exactly_one_row_writes_no_audit():
    """The requirement is explicitly '> 1', not '>= 1' -- a single reviewed
    +assigned row is not notable enough to flag."""
    cur = _AuditFakeCursor(protected_count=1)
    count = repository.record_protected_backup_snapshot(cur, "NMA", 42)
    assert count == 1
    assert _audit_inserts(cur) == []


def test_protected_snapshot_multiple_rows_writes_audit_entry():
    cur = _AuditFakeCursor(protected_count=5)
    count = repository.record_protected_backup_snapshot(cur, "NMA", 42)
    assert count == 5
    audit_calls = _audit_inserts(cur)
    assert len(audit_calls) == 1
    # params order: store_name, order_id, product_code(None), action, old_value(None), new_value, actor(None)
    store_name, order_id, product_code, action, old_value, new_value, actor = audit_calls[0]
    assert order_id == 42
    assert action == "PROTECTED_BACKUP_SNAPSHOT"
    assert "5 reviewed+assigned" in new_value


def test_protected_snapshot_none_order_id_is_a_noop():
    cur = _AuditFakeCursor(protected_count=0)
    count = repository.record_protected_backup_snapshot(cur, "NMA", None)
    assert count == 0
    assert cur.calls == []


def test_protected_snapshot_does_not_change_what_gets_backed_up():
    """This is an audit SIGNAL only -- it must never itself write to
    OrderManagementBackup or touch OrderManagement; the existing
    unconditional backup in insert_data_into_destination is unchanged."""
    cur = _AuditFakeCursor(protected_count=5)
    repository.record_protected_backup_snapshot(cur, "NMA", 42)
    assert not any("OrderManagementBackup" in sql for sql, _ in cur.calls)
    assert not any(sql.strip().upper().startswith("UPDATE OrderManagement".upper())
                   for sql, _ in cur.calls)


# ===========================================================================
# D. restorable_order_preview / restore_backup_order (REPOSITORY)
# ===========================================================================

class _RestoreFakeCursor:
    """Fake cursor for restore_backup_order. The 'locked' flag simulates
    pending Status=0 export lines (the new PendingExportBlocked path) by
    returning a non-zero count from the Status=0 COUNT query that
    pending_export_count_on_connection issues, rather than a
    LegacyOrderProcessingLock row (that table is gone)."""
    def __init__(self, backup_rows, live_codes, locked=False, pending_count=0):
        self.backup_rows = backup_rows
        self.live_codes = live_codes
        # locked=True => simulate pending Status=0 lines
        self.pending_count = 1 if locked else pending_count
        self.calls = []
        self.audit_params = []
        self.last = ""
        self.rowcount = 0

    def execute(self, sql, *params):
        self.last = sql.strip()
        self.calls.append(self.last)
        self.audit_params.append((self.last, params))
        if "UPDATE om SET" in self.last and "OrderManagementBackup omb" in self.last:
            self.rowcount = len(self.backup_rows)
        return self

    def fetchone(self):
        last = self.last
        # _with_store_applock executes sp_getapplock; return None (no result set)
        if "sp_getapplock" in last:
            return None
        if "MAX(OrderId)" in last:
            return (42,)
        # pending_export_count_on_connection: Status=0 count on current order
        if "Status = 0" in last and "COUNT(*)" in last:
            return (self.pending_count,)
        if "COUNT(*) FROM OrderManagement" in last and "QtyCheck" not in last:
            return (self.pending_count,)
        if "COUNT(*) AS ProductCount" in last:
            if not self.backup_rows:
                return None

            class Row:
                ProductCount = len(self.backup_rows)
                BackedUpAt = datetime.datetime(2026, 1, 1, 9, 0)
            return Row()
        return None

    def fetchall(self):
        last = self.last
        if "FROM OrderManagementBackup WHERE StoreName = ? AND OrderId = ?" in last:
            return self.backup_rows
        if "ProductCode FROM OrderManagement" in last and "IN (" in last:
            return [(code,) for code in self.live_codes]
        if "DISTINCT OrderId FROM OrderManagement" in last:
            class Row:
                OrderId = 42
            return [Row()]
        if "ProductCode, Status, OrQty FROM OrderManagement" in last:
            return []
        if "OrSupplierCode, OrSupplier" in last:  # previous_order_suppliers
            return []
        return []

    def nextset(self):
        return False


class _BackupRow:
    def __init__(self, product_code, **kw):
        self.ProductCode = product_code
        self.ProductName = kw.get("ProductName", "Product")
        self.OrQty = kw.get("OrQty", 5)
        self.OrderQty = kw.get("OrderQty", 5)
        self.OrgOrderQty = kw.get("OrgOrderQty", 5)
        self.OrSupplier = kw.get("OrSupplier", "ACME")
        self.OrSupplierCode = kw.get("OrSupplierCode", "S1")
        self.Status = kw.get("Status", 1)
        self.QtyCheck = kw.get("QtyCheck", 1)
        self.Remarks = kw.get("Remarks", None)
        self.WantedType = kw.get("WantedType", "Normal")


class _RestoreFakeConn:
    def __init__(self, cur):
        self.cur = cur
        self.committed = 0
        self.rolled_back = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_restorable_order_preview_none_when_no_backup(monkeypatch):
    cur = _RestoreFakeCursor(backup_rows=[], live_codes=[])
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: _RestoreFakeConn(cur))

    assert repository.restorable_order_preview("NMA", 42) is None


def test_restorable_order_preview_returns_count_and_timestamp(monkeypatch):
    rows = [_BackupRow(1), _BackupRow(2)]
    cur = _RestoreFakeCursor(backup_rows=rows, live_codes=[1, 2])
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: _RestoreFakeConn(cur))

    preview = repository.restorable_order_preview("NMA", 42)

    assert preview["product_count"] == 2
    assert preview["order_id"] == 42
    assert preview["store_name"] == "NMA"


def test_restore_rejects_when_no_backup_exists(monkeypatch):
    cur = _RestoreFakeCursor(backup_rows=[], live_codes=[])
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: _RestoreFakeConn(cur))

    with pytest.raises(repository.RestoreValidationError, match="No backup exists"):
        repository.restore_backup_order("NMA", 42, "admin1")


def test_restore_rejects_when_backup_product_has_no_live_row(monkeypatch):
    """A backup row referencing a product that no longer exists on the
    current order must block the WHOLE restore, not partially apply."""
    rows = [_BackupRow(1), _BackupRow(2)]
    cur = _RestoreFakeCursor(backup_rows=rows, live_codes=[1])  # product 2 missing
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: _RestoreFakeConn(cur))

    with pytest.raises(repository.RestoreValidationError, match="no matching current order row"):
        repository.restore_backup_order("NMA", 42, "admin1")

    assert not any("UPDATE om SET" in c for c in cur.calls), (
        "no partial write may occur when validation fails"
    )


def test_restore_rejects_when_store_is_locked_pending_export(monkeypatch):
    """Restoring over a store with unexported pending lines would silently
    discard that unexported work -- must be refused exactly like Order
    Process is, via the SAME require_no_pending_export_on_connection check."""
    rows = [_BackupRow(1)]
    cur = _RestoreFakeCursor(backup_rows=rows, live_codes=[1], locked=True)
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: _RestoreFakeConn(cur))

    with pytest.raises(repository.PendingExportBlocked):
        repository.restore_backup_order("NMA", 42, "admin1")

    assert not any("UPDATE om SET" in c for c in cur.calls)


def test_restore_succeeds_and_commits_when_all_products_match(monkeypatch):
    rows = [_BackupRow(1), _BackupRow(2)]
    cur = _RestoreFakeCursor(backup_rows=rows, live_codes=[1, 2])
    conn = _RestoreFakeConn(cur)
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: conn)

    result = repository.restore_backup_order("NMA", 42, "admin1")

    assert result["restored_count"] == 2
    assert result["source_order_id"] == 42
    assert result["actor"] == "admin1"
    assert conn.committed == 1
    assert conn.rolled_back == 0
    assert any("UPDATE om SET" in c for c in cur.calls)
    audit_calls = [
        p for sql, p in cur.audit_params
        if sql.startswith("INSERT dbo.LegacyOrderWorkflowAudit")
    ]
    assert any(p[3] == "ORDER_RESTORED" for p in audit_calls)
    assert any(p[3] == "ORDER_LINE_RESTORED" for p in audit_calls)


def test_restore_rolls_back_on_unexpected_error(monkeypatch):
    class ExplodingCursor(_RestoreFakeCursor):
        def execute(self, sql, *params):
            super().execute(sql, *params)
            if "UPDATE om SET" in self.last:
                raise RuntimeError("simulated failure")
            return self

    rows = [_BackupRow(1)]
    cur = ExplodingCursor(backup_rows=rows, live_codes=[1])
    conn = _RestoreFakeConn(cur)
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: conn)

    with pytest.raises(RuntimeError):
        repository.restore_backup_order("NMA", 42, "admin1")

    assert conn.committed == 0
    assert conn.rolled_back == 1


# ===========================================================================
# D/E. Router-level authorization for restore endpoints (no DB needed)
# ===========================================================================

def test_restorable_preview_requires_admin():
    with pytest.raises(HTTPException) as ei:
        lo_router.require_admin({"username": "store_user", "scope": "store"})
    assert ei.value.status_code == 403


def test_restore_endpoint_requires_admin():
    with pytest.raises(HTTPException) as ei:
        lo_router.require_admin({"username": "store_user", "scope": "store"})
    assert ei.value.status_code == 403


def test_restore_endpoint_maps_validation_error_to_409(monkeypatch):
    def raise_validation(sn, oid, actor):
        raise repository.RestoreValidationError("no backup")

    monkeypatch.setattr(lo_router.repository, "restore_backup_order", raise_validation)

    with pytest.raises(HTTPException) as ei:
        lo_router.restore_backup_order(
            "NMA", lo_router.RestoreBackupOrderRequest(order_id=42),
            current_user={"username": "admin1"},
        )
    assert ei.value.status_code == 409


def test_restore_endpoint_maps_lock_active_to_409(monkeypatch):
    """PendingExportBlocked (Status=0 lines still pending export) maps to
    409 -- same as other validation failures -- not 423 (HTTP 423 Locked is
    for durable server-side locks; this is a transient data-state block that
    resolves as soon as the pending lines are exported or cleared)."""
    def raise_locked(sn, oid, actor):
        raise repository.PendingExportBlocked(sn, oid, 2)

    monkeypatch.setattr(lo_router.repository, "restore_backup_order", raise_locked)

    with pytest.raises(HTTPException) as ei:
        lo_router.restore_backup_order(
            "NMA", lo_router.RestoreBackupOrderRequest(order_id=42),
            current_user={"username": "admin1"},
        )
    assert ei.value.status_code == 409


def test_restorable_preview_endpoint_404_when_none(monkeypatch):
    monkeypatch.setattr(lo_router.repository, "restorable_order_preview", lambda sn, oid: None)

    with pytest.raises(HTTPException) as ei:
        lo_router.restorable_order_preview("NMA", 42, current_user={"username": "admin1"})
    assert ei.value.status_code == 404
