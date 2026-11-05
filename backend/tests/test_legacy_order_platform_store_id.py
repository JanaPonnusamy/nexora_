"""platform_store_id must stay tenant-correct when one store_code exists under two
tenants (.32: Success's SMA and the SMS group's SMA) -- a legacy order for one
tenant's store must never be built from the other tenant's sync.* data."""
from __future__ import annotations

import pytest

from modules.legacy_order import database

SUCCESS = "A6132E5C-9198-4837-8A42-3D2C326E9E12"
SMS = "2D5ED813-881C-4CCA-803D-9FC78A15B85A"


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self

    def execute(self, *_):
        return self

    def fetchall(self):
        return self.rows


@pytest.fixture
def platform(monkeypatch):
    def use(rows, central_tenant=None):
        monkeypatch.setattr(database, "platform_connection_string", lambda: "fake")
        monkeypatch.setattr(database.pyodbc, "connect", lambda *a, **k: _Conn(rows))
        calls = []

        def tenant(store_name):
            calls.append(store_name)
            return central_tenant

        monkeypatch.setattr(database, "central_store_tenant", tenant)
        return calls
    return use


def test_unique_code_needs_no_central_lookup(platform):
    calls = platform([("ID-SMG", SMS)])
    assert database.platform_store_id("SMG") == "ID-SMG"
    assert calls == []


def test_shared_code_follows_the_central_rows_tenant(platform):
    calls = platform([("ID-SMS-SMA", SMS), ("ID-SUCCESS-SMA", SUCCESS)], central_tenant=SUCCESS.lower())
    assert database.platform_store_id("SMA") == "ID-SUCCESS-SMA"
    assert calls == ["SMA"]


def test_shared_code_without_a_central_tenant_is_not_guessed(platform):
    platform([("ID-SMS-SMA", SMS), ("ID-SUCCESS-SMA", SUCCESS)], central_tenant=None)
    assert database.platform_store_id("SMA") is None


def test_unknown_code(platform):
    platform([])
    assert database.platform_store_id("NOPE") is None
