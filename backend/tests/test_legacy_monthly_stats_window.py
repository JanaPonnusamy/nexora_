"""qty_check_monthly_stats window: the legacy default (current month + 3
before, used by the Order Workspace and web) is unchanged; `months` (the
Procurement Monthly Trend) widens it to that many calendar months."""
from __future__ import annotations

from modules.legacy_order import repository


class _Cursor:
    def __init__(self, seen):
        self.seen, self.description = seen, []

    def execute(self, sql, params):
        self.seen.append(sql)

    def fetchall(self):
        return []


class _Conn:
    def __init__(self, seen):
        self.seen = seen

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return _Cursor(self.seen)


def _sqls(monkeypatch, **kw):
    seen = []
    monkeypatch.setattr(repository.database, "get_central_connection", lambda: _Conn(seen))
    assert repository.qty_check_monthly_stats({"store_name": "NMW"}, 5433, "local", **kw) == []
    return seen


def test_default_window_is_the_legacy_four_months(monkeypatch):
    for sql in _sqls(monkeypatch):
        assert "DATEDIFF(MONTH, 0, GETDATE()) - 3, 0)" in sql


def test_months_widens_the_window(monkeypatch):
    for sql in _sqls(monkeypatch, months=6):
        assert "DATEDIFF(MONTH, 0, GETDATE()) - 5, 0)" in sql
