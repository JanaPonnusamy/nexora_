"""Skip rules on the legacy order (platform skip modes on OrderNMC)."""
from __future__ import annotations

import pytest

from modules.legacy_order import order_process, repository


def test_skip_product_rejects_unknown_mode():
    with pytest.raises(ValueError):
        repository.skip_product("NMS", 42, "forever")


def test_skip_modes_match_platform():
    """Same codes as frontend/src/components/procurement/skipModes.ts; only
    the two 'until next' modes carry into later orders."""
    assert set(repository.SKIP_MODES) == {"current_refresh", "until_next_sales", "until_next_demand"}
    assert set(repository.PERSISTENT_SKIP_MODES) == {"until_next_sales", "until_next_demand"}


def test_order_generation_reapplies_carried_skips_inside_the_transaction(monkeypatch):
    """Schema is ensured BEFORE the order transaction (its DDL runs on its
    own connection and would block on this run's locks); carried skips are
    re-applied after the new rows are inserted and before the commit."""
    events = []

    class FakeCursor:
        rowcount = 0
        fast_executemany = False

        def execute(self, sql, *params):
            if "INSERT INTO OrderManagement" in sql and "Backup" not in sql:
                events.append("insert")
            return self

        def executemany(self, sql, params_seq):
            events.append("insert")
            return self

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class FakeConn:
        timeout = 0

        def cursor(self):
            return FakeCursor()

        def commit(self):
            events.append("commit")

        def rollback(self):
            events.append("rollback")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(order_process, "_connect", lambda cs, timeout=30: FakeConn())
    monkeypatch.setattr(order_process.repository, "_with_store_applock", lambda cur, sn: None)
    monkeypatch.setattr(order_process.repository, "record_protected_backup_snapshot", lambda *a: None)
    monkeypatch.setattr(order_process.repository, "_latest_order_id", lambda cur, sn: None)
    monkeypatch.setattr(order_process.repository, "_ensure_skip_schema", lambda cur=None: events.append("schema"))
    monkeypatch.setattr(order_process.repository, "apply_carried_skips", lambda cur, sn: events.append("carry"))
    monkeypatch.setattr(order_process.database, "central_connection_string", lambda: "cs", raising=False)

    columns = [src for src, _ in order_process.COLUMN_MAP]
    row = tuple(20261026120000 if dest == "OrderId" else None for _, dest in order_process.COLUMN_MAP)
    order_process.insert_data_into_destination(columns, [row], "NMS")

    assert events[0] == "schema"
    assert events.index("insert") < events.index("carry") < events.index("commit")
