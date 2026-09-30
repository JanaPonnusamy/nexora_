"""Regression tests for lazy Agent Ops schema provisioning."""

from modules.agent_ops import repository


class _Cursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))


class _Connection:
    def __init__(self):
        self.cur = _Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closes += 1


def test_ensure_schema_applies_idempotent_migration_once(monkeypatch):
    connections = []

    def connect():
        connection = _Connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(repository, "get_connection", connect)
    monkeypatch.setattr(repository, "_schema_ready", False)

    repository.ensure_schema()
    repository.ensure_schema()

    assert len(connections) == 1
    assert connections[0].commits == 1
    assert connections[0].rollbacks == 0
    assert connections[0].closes == 1
    sql = "\n".join(statement for statement, _ in connections[0].cur.executed)
    assert "agent_watchdog_audit" in sql
    assert "agent_watchdog_status" in sql
