"""Tests for Legacy Order's pending-supplier-assignment confirmation gate,
short-lived concurrency lock on Order Process, and restore-path pending export block.

Architecture Context:
---------------------
The old durable ``dbo.LegacyOrderProcessingLock`` table and manual unlock mechanism
(``acquire_processing_lock_if_pending``, ``unlock_processing_lock``,
``processing_lock_status``, ``require_unlocked_for_processing``) have been completely
removed.

The new design features:
1. QtyCheckConfirmationRequired:
   - Warning gate when current-date order has > 1 product pending supplier assignment
     (qty_check = 1 AND status = 0).
   - If count <= 1, processing proceeds unconditionally.
   - If count > 1, the caller must acknowledge with `confirmed=True`. This is an
     ordinary confirmation available to any authenticated caller -- not a
     privileged/admin-only action.
2. State Revalidation (Requirement 8):
   - Confirming requires `confirmed_order_id` and `confirmed_count`.
   - If live count or order ID changed since preview, renewed confirmation is required.
3. PendingExportBlocked (Restore Path Only):
   - Hard, non-overridable block on `restore_backup_order` when Status = 0 lines exist.
   - Order Process does NOT use this.
5. Short-lived Concurrency Guard (_with_store_applock):
   - Transaction-scoped `sp_getapplock` taken in `insert_data_into_destination`
     immediately before destructive writes, preventing concurrent runs for the same store.
6. Absence of durable lock:
   - No durable lock table, no unlock endpoints, no timeout background threads.
"""
from __future__ import annotations

import inspect
import pytest
from fastapi import HTTPException

from modules.legacy_order import database, order_process, repository, router as lo_router, schemas, service


_NMA_STORE = {
    "store_name": "NMA",
    "store_code": "1",
    "server_name": "SRV",
    "database": "NMA_DB",
    "username": "u",
    "password": "p",
}

ADMIN_USER = {
    "is_platform_user": True,
    "role_names": ["PLATFORM_OWNER"],
    "store_code": None,
    "sub": "a1",
    "username": "admin",
}

NON_ADMIN_USER = {
    "is_platform_user": False,
    "role_names": ["PURCHASE_MANAGER"],
    "store_code": "NMA",
    "sub": "u1",
    "username": "pm",
}


class FakeThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}

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
    """Store resolves cleanly, no job already running, branch connects ok,
    and the store's latest order is today's."""
    monkeypatch.setattr(service, "_resolve_store", lambda sn: dict(_NMA_STORE))
    monkeypatch.setattr(service, "_running_job_kind", lambda sn: None)
    monkeypatch.setattr(service.repository, "test_branch_connection", lambda store: (True, None))
    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", lambda sn: None)


# ===========================================================================
# 1. UNIT: Qty Check Confirmation Gate (service.start_order_process)
# ===========================================================================

def test_process_proceeds_with_zero_matching_products(base_env, thread_spy, monkeypatch):
    """Count = 0: no pending supplier assignment rows, proceeds unconditionally."""
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (42, 0, []))

    job_id = service.start_order_process("NMA")

    assert job_id is not None
    assert len(thread_spy) == 1


def test_process_proceeds_with_one_matching_product(base_env, thread_spy, monkeypatch):
    """Count = 1: threshold is > 1 products, so 1 product proceeds without warning."""
    sample = [{"code": 101, "name": "Item A"}]
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (42, 1, sample))

    job_id = service.start_order_process("NMA")

    assert job_id is not None
    assert len(thread_spy) == 1


def test_process_requires_confirmation_with_multiple_matching_products(base_env, thread_spy, monkeypatch):
    """Count > 1 without override: raises QtyCheckConfirmationRequired."""
    sample = [{"code": 101, "name": "Item A"}, {"code": 102, "name": "Item B"}]
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (42, 2, sample))

    with pytest.raises(service.QtyCheckConfirmationRequired) as ei:
        service.start_order_process("NMA")

    assert ei.value.order_id == 42
    assert ei.value.count == 2
    assert ei.value.sample == sample
    assert not thread_spy


def test_confirmed_without_matching_ids_still_raises(base_env, thread_spy, monkeypatch):
    """confirmed=True alone (no matching confirmed_order_id/confirmed_count) still raises."""
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (42, 2, []))

    with pytest.raises(service.QtyCheckConfirmationRequired):
        service.start_order_process("NMA", confirmed=True)

    assert not thread_spy


def test_confirmed_by_non_admin_with_matching_confirmation_proceeds(base_env, thread_spy, monkeypatch):
    """Confirming the warning is an ordinary action -- a non-admin caller may do it."""
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (42, 2, []))

    job_id = service.start_order_process(
        "NMA",
        confirmed=True,
        confirmed_order_id=42,
        confirmed_count=2,
    )

    assert job_id is not None
    assert len(thread_spy) == 1


def test_stale_confirmation_rejected_when_count_changed(base_env, thread_spy, monkeypatch):
    """Requirement 8: If confirmed_count does not match live count, revalidation fails."""
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (42, 5, []))

    with pytest.raises(service.QtyCheckConfirmationRequired) as ei:
        service.start_order_process(
            "NMA",
            confirmed=True,
            confirmed_order_id=42,
            confirmed_count=2,  # Stale preview saw 2, live is now 5
        )

    assert ei.value.count == 5
    assert not thread_spy


def test_stale_confirmation_rejected_when_order_id_changed(base_env, thread_spy, monkeypatch):
    """Requirement 8: If confirmed_order_id does not match live order_id, revalidation fails."""
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (43, 2, []))

    with pytest.raises(service.QtyCheckConfirmationRequired) as ei:
        service.start_order_process(
            "NMA",
            confirmed=True,
            confirmed_order_id=42,  # Stale preview saw order 42, live is now 43
            confirmed_count=2,
        )

    assert ei.value.order_id == 43
    assert not thread_spy


def test_stale_current_order_rejected(base_env, thread_spy, monkeypatch):
    """If latest order is not today's, raises StaleCurrentOrder."""
    def fail_stale(sn):
        raise repository.NoCurrentDateOrder(sn, "Order is from yesterday")

    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", fail_stale)

    with pytest.raises(service.StaleCurrentOrder):
        service.start_order_process("NMA")

    assert not thread_spy


def test_concurrent_job_rejected(monkeypatch):
    """If another job is already running for the store, rejects with 409-style ValueError."""
    monkeypatch.setattr(service, "_resolve_store", lambda sn: dict(_NMA_STORE))
    monkeypatch.setattr(service, "_running_job_kind", lambda sn: "sync")

    with pytest.raises(ValueError, match="already running"):
        service.start_order_process("NMA")


# ===========================================================================
# 2. ROUTER: Confirming the warning is an ordinary action (no admin gate)
# ===========================================================================

def test_router_non_admin_can_confirm_and_proceed(monkeypatch, thread_spy):
    """Confirming the pending-supplier-assignment warning is not privileged --
    a non-admin user sending confirmed=True with a matching snapshot succeeds."""
    monkeypatch.setattr(lo_router.service, "start_order_process", service.start_order_process)
    monkeypatch.setattr(service, "_resolve_store", lambda sn: dict(_NMA_STORE))
    monkeypatch.setattr(service, "_running_job_kind", lambda sn: None)
    monkeypatch.setattr(service.repository, "require_current_date_order_if_any", lambda sn: None)
    monkeypatch.setattr(service.repository, "qty_check_confirmation_count", lambda sn: (42, 3, []))
    monkeypatch.setattr(service.repository, "test_branch_connection", lambda store: (True, None))

    payload = schemas.OrderProcessRequest(
        store_name="NMA",
        confirmed=True,
        confirmed_order_id=42,
        confirmed_count=3,
    )

    result = lo_router.start_order_process(payload, current_user=NON_ADMIN_USER)

    assert result.job_id is not None
    assert len(thread_spy) == 1


def test_router_confirmed_succeeds_for_admin_user_too(monkeypatch):
    """An admin user confirming the warning also succeeds (no special path needed)."""
    monkeypatch.setattr(lo_router.service, "start_order_process", lambda *a, **k: "job-123")

    payload = schemas.OrderProcessRequest(
        store_name="NMA",
        confirmed=True,
        confirmed_order_id=42,
        confirmed_count=3,
    )

    res = lo_router.start_order_process(payload, current_user=ADMIN_USER)
    assert res.job_id == "job-123"


def test_router_qty_check_confirmation_required_maps_to_409(monkeypatch):
    """QtyCheckConfirmationRequired maps to HTTP 409 Conflict."""
    def fake_start(*a, **k):
        raise service.QtyCheckConfirmationRequired(42, 3, [{"code": 1, "name": "A"}])

    monkeypatch.setattr(lo_router.service, "start_order_process", fake_start)

    payload = schemas.OrderProcessRequest(store_name="NMA")
    with pytest.raises(HTTPException) as ei:
        lo_router.start_order_process(payload, current_user=ADMIN_USER)

    assert ei.value.status_code == 409
    assert "3 products are pending supplier assignment" in ei.value.detail


def test_router_preview_endpoint(monkeypatch):
    """GET /orders/{store_name}/qty-check-confirmation returns order_id, count, sample."""
    sample = [{"code": 101, "name": "Prod A"}]
    monkeypatch.setattr(repository, "qty_check_confirmation_count", lambda sn: (42, 1, sample))

    data = lo_router.qty_check_confirmation("NMA")
    assert data == {"order_id": 42, "count": 1, "sample": sample}


# ===========================================================================
# 3. RESTORE-PATH HARD BLOCK: PendingExportBlocked & require_no_pending_export
# ===========================================================================

def test_require_no_pending_export_raises_when_pending_rows_exist():
    """require_no_pending_export_on_connection raises PendingExportBlocked when Status=0 count > 0."""
    calls = []

    class FakeCursor:
        def execute(self, sql, *params):
            calls.append((sql.strip(), params))
            return self

        def fetchone(self):
            last_sql = calls[-1][0]
            if "MAX(OrderId)" in last_sql:
                return (42,)
            if "COUNT(*) FROM OrderManagement" in last_sql and "Status = 0" in last_sql:
                return (3,)
            return None

        def nextset(self):
            return False

    cur = FakeCursor()
    with pytest.raises(repository.PendingExportBlocked) as ei:
        repository.require_no_pending_export_on_connection(cur, "NMA")

    assert ei.value.store_name == "NMA"
    assert ei.value.order_id == 42
    assert ei.value.count == 3

    # Verified that applock was acquired first
    assert any("sp_getapplock" in sql for sql, _ in calls)


def test_require_no_pending_export_proceeds_when_no_pending_rows():
    """require_no_pending_export_on_connection does not raise when Status=0 count == 0."""
    calls = []

    class FakeCursor:
        def execute(self, sql, *params):
            calls.append((sql.strip(), params))
            return self

        def fetchone(self):
            last_sql = calls[-1][0]
            if "MAX(OrderId)" in last_sql:
                return (42,)
            if "COUNT(*) FROM OrderManagement" in last_sql and "Status = 0" in last_sql:
                return (0,)
            return None

        def nextset(self):
            return False

    cur = FakeCursor()
    repository.require_no_pending_export_on_connection(cur, "NMA")
    assert any("sp_getapplock" in sql for sql, _ in calls)


def test_require_no_pending_export_proceeds_when_no_order_exists():
    """require_no_pending_export_on_connection does not raise when store has no orders at all."""
    calls = []

    class FakeCursor:
        def execute(self, sql, *params):
            calls.append((sql.strip(), params))
            return self

        def fetchone(self):
            return None

        def nextset(self):
            return False

    cur = FakeCursor()
    repository.require_no_pending_export_on_connection(cur, "NMA")
    assert any("sp_getapplock" in sql for sql, _ in calls)


# ===========================================================================
# 4. REPOSITORY SQL SHAPE: pending_export_count and qty_check_confirmation_count
# ===========================================================================

def test_pending_export_count_sql_shape(monkeypatch):
    """Verifies SQL text and params for pending_export_count_on_connection."""
    calls = []

    class FakeCursor:
        def execute(self, sql, *params):
            calls.append((sql.strip(), params))
            return self

        def fetchone(self):
            last_sql = calls[-1][0]
            if "MAX(OrderId)" in last_sql:
                return (100,)
            if "COUNT(*) FROM OrderManagement" in last_sql:
                return (4,)
            return None

    cur = FakeCursor()
    order_id, count = repository.pending_export_count_on_connection(cur, "NMA")
    assert order_id == 100
    assert count == 4

    sql_texts = [c[0] for c in calls]
    assert any("MAX(OrderId)" in s and "StoreName = ?" in s for s in sql_texts)
    assert any("Status = 0" in s and "StoreName = ?" in s and "OrderId = ?" in s for s in sql_texts)


def test_qty_check_confirmation_count_sql_shape(monkeypatch):
    """Verifies SQL text and params for qty_check_confirmation_count."""
    calls = []

    class FakeCursor:
        def execute(self, sql, *params):
            calls.append((sql.strip(), params))
            return self

        def fetchone(self):
            return (55,)

        def fetchall(self):
            return [(1, "Prod A"), (2, "Prod B")]

    class FakeConn:
        def cursor(self):
            return FakeCursor()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(database, "get_central_connection", lambda: FakeConn())

    order_id, count, sample = repository.qty_check_confirmation_count("NMA")
    assert order_id == 55
    assert count == 2
    assert sample == [{"product_code": 1, "product_name": "Prod A"}, {"product_code": 2, "product_name": "Prod B"}]

    sql_texts = [c[0] for c in calls]
    assert any("qtycheck = 1" in s and "status = 0" in s for s in sql_texts)


# ===========================================================================
# 5. CONCURRENCY GUARD: _with_store_applock in insert_data_into_destination
# ===========================================================================

def test_with_store_applock_executes_sp_getapplock_transaction_scoped():
    """_with_store_applock executes sp_getapplock with @LockOwner='Transaction' and store prefix."""
    calls = []

    class FakeCursor:
        def execute(self, sql, *params):
            calls.append((sql.strip(), params))
            return self

        def nextset(self):
            return False

    cur = FakeCursor()
    repository._with_store_applock(cur, "NMA")

    assert len(calls) == 1
    sql, params = calls[0]
    assert "sp_getapplock" in sql
    assert "@LockMode = 'Exclusive'" in sql
    assert "@LockOwner = 'Transaction'" in sql
    assert params[0] == f"{repository._LOCK_APPLOCK_PREFIX}NMA"
    assert params[1] == "NMA"


def test_insert_data_into_destination_acquires_applock_before_writes(monkeypatch):
    """insert_data_into_destination invokes _with_store_applock inside the transaction
    before clearing backup or inserting rows."""
    events = []

    def fake_applock(cur, sn):
        events.append("applock")

    class FakeCursor:
        def execute(self, sql, *params):
            s = sql.strip()
            if "DELETE FROM OrderManagementBackup" in s:
                events.append("delete_backup")
            elif "INSERT INTO OrderManagementBackup" in s:
                events.append("insert_backup")
            elif "DELETE FROM OrderManagement" in s:
                events.append("delete_ordermanagement")
            elif "INSERT INTO OrderManagement" in s:
                events.append("insert_ordermanagement")
            return self

        def executemany(self, sql, params_seq):
            s = sql.strip()
            if "INSERT INTO OrderManagement" in s:
                events.append("insert_ordermanagement")
            return self

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class FakeConn:
        def __init__(self):
            self.committed = False
            self.rolled_back = False
            self.timeout = 0

        def cursor(self):
            return FakeCursor()

        def commit(self):
            self.committed = True
            events.append("commit")

        def rollback(self):
            self.rolled_back = True
            events.append("rollback")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, *a):
            if exc_type:
                self.rollback()
            return False

    conn = FakeConn()
    monkeypatch.setattr(order_process, "_connect", lambda cs, timeout=30: conn)
    monkeypatch.setattr(order_process.repository, "_with_store_applock", fake_applock)
    monkeypatch.setattr(order_process.repository, "_ensure_workflow_schema", lambda cur: None)
    # Skip rules: schema is applied on its own connection; carry-forward is
    # covered by its own test -- neither is what this test is about.
    monkeypatch.setattr(order_process.repository, "_ensure_skip_schema", lambda cur=None: None)
    monkeypatch.setattr(order_process.repository, "apply_carried_skips", lambda cur, sn: 0)
    monkeypatch.setattr(order_process.repository, "record_protected_backup_snapshot", lambda cur, sn, oid: None)
    monkeypatch.setattr(order_process.repository, "_latest_order_id", lambda cur, sn: 42)

    columns = [src for src, _ in order_process.COLUMN_MAP]
    rows = [[42 if c == "OrderId" else "val" for c in columns]]
    total = order_process.insert_data_into_destination(columns, rows, "NMA")

    assert total == 1
    assert conn.committed
    assert events[0] == "applock", "sp_getapplock must precede all destructive table writes"
    assert "delete_backup" in events
    assert "commit" in events


def test_insert_data_into_destination_rolls_back_on_error(monkeypatch):
    """When an exception occurs inside insert_data_into_destination, transaction is rolled back."""
    rolled_back = []

    class BadCursor:
        def execute(self, sql, *params):
            if "DELETE FROM OrderManagementBackup" in sql:
                raise RuntimeError("simulated disk error during backup clear")
            return self

        def fetchone(self):
            return None

    class FakeConn:
        def __init__(self):
            self.timeout = 0

        def cursor(self):
            return BadCursor()

        def commit(self):
            pass

        def rollback(self):
            rolled_back.append(True)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, *a):
            if exc_type:
                self.rollback()
            return False

    monkeypatch.setattr(order_process, "_connect", lambda cs, timeout=30: FakeConn())
    monkeypatch.setattr(order_process.repository, "_with_store_applock", lambda cur, sn: None)
    monkeypatch.setattr(order_process.repository, "_ensure_workflow_schema", lambda cur: None)
    monkeypatch.setattr(order_process.repository, "record_protected_backup_snapshot", lambda cur, sn, oid: None)
    monkeypatch.setattr(order_process.repository, "_latest_order_id", lambda cur, sn: 42)

    columns = [src for src, _ in order_process.COLUMN_MAP]
    rows = [[42 if c == "OrderId" else "val" for c in columns]]
    with pytest.raises(RuntimeError, match="simulated disk error"):
        order_process.insert_data_into_destination(columns, rows, "NMA")

    assert len(rolled_back) == 1


# ===========================================================================
# 6. STRUCTURAL VERIFICATION: Old Lock Mechanism Completely Removed
# ===========================================================================

def test_old_durable_lock_functions_are_removed():
    """Verify that the old durable lock functions are gone from repository."""
    assert not hasattr(repository, "acquire_processing_lock_if_pending")
    assert not hasattr(repository, "unlock_processing_lock")
    assert not hasattr(repository, "processing_lock_status")
    assert not hasattr(repository, "require_unlocked_for_processing")
    assert not hasattr(service, "ProcessingLocked")


def test_job_completion_or_failure_does_not_touch_any_lock():
    """Job status updates and completions have no references to locks."""
    # Ensure repository has no unlock call that could be invoked
    assert not hasattr(repository, "unlock_processing_lock")

    job_id = service._new_job("order", "NMA", 1)
    service._update(job_id, status="completed", message="Done")
    job = service.get_job(job_id)
    assert job["status"] == "completed"

    job_fail_id = service._new_job("order", "NMA", 1)
    service._update(job_fail_id, status="failed", error="Failure")
    failed_job = service.get_job(job_fail_id)
    assert failed_job["status"] == "failed"


def test_no_automatic_timeout_or_background_unlock():
    """Inspect order_process, service, and repository sources: verify no SQL queries
    the deleted table dbo.LegacyOrderProcessingLock and no unlock functions exist."""
    for mod in (repository, service, order_process):
        source = inspect.getsource(mod)
        # Table must never be queried or written to
        assert "FROM dbo.LegacyOrderProcessingLock" not in source
        assert "INTO dbo.LegacyOrderProcessingLock" not in source
        assert "MERGE dbo.LegacyOrderProcessingLock" not in source
        assert "unlock_processing_lock" not in source
        assert "acquire_processing_lock_if_pending" not in source
