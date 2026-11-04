"""Offline tests for the OrderNMC mirror (HO module + agent applier SQL)."""
from __future__ import annotations

import datetime
import decimal
import gzip
import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.ordernmc_mirror import catalog, repository, router, service, sql_builder

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from store_agent import ordernmc_mirror as agent  # noqa: E402


def _col(name, type_, max_length=4, precision=0, scale=0, nullable=True, identity=False):
    return {"name": name, "type": type_, "max_length": max_length, "precision": precision,
            "scale": scale, "nullable": nullable, "identity": identity}


# ---- sql_builder ----------------------------------------------------------

def test_keyset_where_and_params_composite():
    keys = [_col("A", "int"), _col("B", "nvarchar", 100), _col("C", "datetime", 8)]
    where = sql_builder.keyset_where(keys)
    assert where == ("((t.[A] > ?) OR (t.[A] = ? AND t.[B] > ?) OR "
                     "(t.[A] = ? AND t.[B] = ? AND t.[C] > ?))")
    assert sql_builder.keyset_params([1, "x", "d"]) == [1, 1, "x", 1, "x", "d"]


@pytest.mark.parametrize("col,expected", [
    (_col("a", "nvarchar", 200), "nvarchar(100)"),
    (_col("a", "varchar", -1), "varchar(max)"),
    (_col("a", "decimal", 9, 18, 2), "decimal(18,2)"),
    (_col("a", "datetime2", 8, 27, 7), "datetime2(7)"),
    (_col("a", "int"), "int"),
])
def test_sql_type(col, expected):
    assert sql_builder.sql_type(col) == expected


def test_row_hash_chunks_wide_rows_under_hashbytes_limit():
    cols = [_col(f"c{i}", "nvarchar", 2000) for i in range(6)]  # 6 x 1000 chars
    expr = sql_builder.row_hash_expr(cols)
    # 3 columns fit a 3800-char chunk -> 2 chunk digests + the outer one.
    assert expr.count("HASHBYTES('MD5'") == 2 + 1
    assert expr.startswith("CAST(SUBSTRING(HASHBYTES('MD5', ")


def test_pk_page_sql_param_order_shape():
    cols = [_col("ID", "int"), _col("StoreName", "nvarchar", 100), _col("Qty", "float", 8)]
    sql = sql_builder.pk_page_sql("PurchaseTrans", cols, cols[:2], has_cursor=True)
    assert sql.count("?") == 1 + 3 + 3  # TOP, keyset(2 keys -> 3), target/table/rn
    assert "FROM [dbo].[PurchaseTrans] AS t WHERE" in sql
    assert "OR p.__rn = ?" in sql


def test_store_scoped_sql_filters_before_keyset_and_ledger():
    cols = [_col("ID", "int"), _col("StoreName", "nvarchar", 100), _col("Qty", "float", 8)]
    sql = sql_builder.pk_page_sql("PurchaseTrans", cols, cols[:2], has_cursor=True,
                                  store_column="StoreName", n_stores=2)
    assert sql.count("?") == 1 + 2 + 3 + 3  # TOP, stores, keyset, target/table/rn
    assert "WHERE t.[StoreName] IN (?, ?) AND ((t.[ID] > ?)" in sql
    first = sql_builder.pk_page_sql("PurchaseTrans", cols, cols[:2], has_cursor=False,
                                    store_column="StoreName", n_stores=1)
    assert "AS t WHERE t.[StoreName] IN (?) ORDER BY" in first
    heap = sql_builder.heap_groups_sql("OrderManagement", cols, cols[:2],
                                       store_column="StoreName", n_stores=2)
    # store params bind first: the filter sits in the first CTE, before TOP (?).
    assert heap.index("IN (?, ?)") < heap.index("TOP (?)")
    assert sql_builder.store_filter(None, 2) == "" and sql_builder.store_filter("StoreName", 0) == ""


def test_store_scoped_target_skips_tables_without_storename():
    from modules.ordernmc_mirror import service
    target = {"stores": " TESTSMG,TESTSMF ,TESTSMG", "tables": None}
    assert service._stores(target) == ["TESTSMF", "TESTSMG"]
    assert service._stores({"stores": None}) == []
    assert service._store_params({"store_column": "StoreName"}, ["A"]) == ["A"]
    assert service._store_params({"store_column": None}, ["A"]) == []
    assert "stores" in catalog.STORE_SCOPED_EXCLUDED


# ---- codec ----------------------------------------------------------------

@pytest.mark.parametrize("type_,value", [
    ("datetime", datetime.datetime(2026, 10, 24, 13, 24, 4, 457000)),
    ("date", datetime.date(2026, 1, 2)),
    ("decimal", decimal.Decimal("12.3400")),
    ("money", decimal.Decimal("1.2345")),
    ("varbinary", b"\x00\xffab"),
    ("nvarchar", "Ä text"),
    ("int", 7),
    ("float", 1.5),
])
def test_codec_roundtrip_backend_and_agent(type_, value):
    wire = json.loads(json.dumps(catalog.encode_value(value)))
    assert catalog.decode_value(type_, wire) == value
    assert agent.decode_value(type_, wire) == value


# ---- table selection ------------------------------------------------------

def test_default_exclusions_and_whitelist(monkeypatch):
    monkeypatch.delenv("ORDERNMC_MIRROR_INCLUDE_TABLES", raising=False)
    monkeypatch.delenv("ORDERNMC_MIRROR_EXCLUDE_TABLES", raising=False)
    assert catalog.is_mirrored("ProductSaleInformation")
    assert catalog.is_mirrored("OrderManagement")
    for infra in ("sync_tasks", "SyncRun", "Users", "sysdiagrams", "SupplierProductMatch_Stage_62d822dc"):
        assert not catalog.is_mirrored(infra)
    monkeypatch.setenv("ORDERNMC_MIRROR_INCLUDE_TABLES", "users")
    assert catalog.is_mirrored("Users")
    assert catalog.is_mirrored("Products", ["prod*"])
    assert not catalog.is_mirrored("Batches", ["prod*"])


# ---- pass scheduling ------------------------------------------------------

def test_needs_pass():
    now = datetime.datetime(2026, 11, 3, 12, 0)
    start = datetime.datetime(2026, 11, 1, 8, 0)
    st = {"last_pass_started_at": now - datetime.timedelta(hours=1),
          "last_pass_completed_at": now - datetime.timedelta(minutes=50)}
    assert service._needs_pass({}, 1, now, start, {})                       # never passed
    assert not service._needs_pass(st, 1, now, start, {})                   # untouched since start
    assert service._needs_pass(st, 1, now, now, {})                         # SQL restarted after pass
    assert service._needs_pass(st, 1, now, start, {1: now})                 # written since
    assert not service._needs_pass(st, 1, now, start, {1: now - datetime.timedelta(hours=3)})
    # untrusted stats (no permission / AUTO_CLOSE): timed rescan, not every cycle
    assert service._needs_pass(st, 1, now, start, None)                     # done 50 min ago
    fresh = dict(st, last_pass_completed_at=now - datetime.timedelta(minutes=5))
    assert not service._needs_pass(fresh, 1, now, start, None)
    old = dict(st, last_pass_completed_at=now - datetime.timedelta(hours=service.FULL_PASS_HOURS + 1))
    assert service._needs_pass(old, 1, now, start, {})                      # periodic full verify


class _Cur:
    def __init__(self, auto_close):
        self.auto_close, self.sql = auto_close, ""

    def execute(self, sql, *a):
        self.sql = sql

    def fetchone(self):
        return (self.auto_close,)

    def fetchall(self):
        return [(7, datetime.datetime(2026, 11, 4, 20, 0))]


class _Conn:
    def __init__(self, auto_close):
        self.auto_close = auto_close

    def cursor(self):
        return _Cur(self.auto_close)


def test_auto_close_database_stats_are_not_trusted():
    assert catalog.last_user_updates(_Conn(True)) is None
    assert catalog.last_user_updates(_Conn(False)) == {7: datetime.datetime(2026, 11, 4, 20, 0)}


# ---- agent apply SQL ------------------------------------------------------

def test_agent_stage_uses_local_column_collation():
    # The SMG store's OrderNMC is CI_AS but OrderSuppliers.suppliercode is CI_AI.
    local = {"suppliercode": {"collation": "Latin1_General_CI_AI"},
             "storename": {"collation": "Latin1_General_CI_AS"}, "id": {"collation": None}}
    assert agent._stage_collate({"name": "suppliercode", "type": "nvarchar"}, local) == \
        " COLLATE Latin1_General_CI_AI"
    assert agent._stage_collate({"name": "New", "type": "varchar"}, local) == " COLLATE DATABASE_DEFAULT"
    assert agent._stage_collate({"name": "ID", "type": "int"}, local) == ""


def test_agent_merge_never_updates_keys_or_identity():
    sql = agent._merge_sql("T", ["Id", "Code", "Name", "Qty"], ["Code"], {"id"})
    assert "WHEN MATCHED AND EXISTS (SELECT S.[Name], S.[Qty] EXCEPT SELECT T.[Name], T.[Qty])" in sql
    assert "T.[Code] = S.[Code]" in sql and "T.[Id] = S.[Id]" not in sql
    assert "WHEN NOT MATCHED BY TARGET THEN INSERT ([Id], [Code], [Name], [Qty])" in sql
    assert "DELETE" not in sql and "NOT MATCHED BY SOURCE" not in sql


def test_agent_replace_deletes_only_matching_key_groups():
    sql = agent._replace_delete_sql("OrderManagement", ["StoreName", "OrderId"])
    assert "INTERSECT SELECT S.[StoreName], S.[OrderId]" in sql
    assert sql.startswith("DELETE T FROM [dbo].[OrderManagement] AS T WHERE EXISTS")


def test_agent_input_sizes_pin_fractional_seconds():
    assert agent._input_size({"type": "datetime", "sql_type": "datetime"})[2] == 3
    assert agent._input_size({"type": "datetime2", "sql_type": "datetime2(7)"})[2] == 7
    assert agent._input_size({"type": "decimal", "sql_type": "decimal(18,4)"})[1:] == (18, 4)
    assert agent._input_size({"type": "nvarchar", "sql_type": "nvarchar(50)"}) is None


# ---- router ---------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(router.agent_router)
    app.dependency_overrides[router.get_current_device] = lambda: {"device_id": "dev-1"}
    return TestClient(app)


def test_pull_is_gzipped_for_gzip_clients(client, monkeypatch):
    rows = [[i, "x" * 50] for i in range(200)]
    monkeypatch.setattr(service, "pull", lambda d: {"status": "batch", "device": d, "rows": rows})
    resp = client.post("/api/ordernmc-mirror/v1/agent/pull", headers={"Accept-Encoding": "gzip"})
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
    assert resp.json()["device"] == "dev-1" and len(resp.json()["rows"]) == 200


def test_ack_unknown_batch_is_409(client, monkeypatch):
    def _ack(*a):
        raise service.MirrorError(409, "Unknown or expired batch")
    monkeypatch.setattr(service, "ack", _ack)
    resp = client.post("/api/ordernmc-mirror/v1/agent/ack", json={"batch_id": "b", "ok": True})
    assert resp.status_code == 409


def test_agent_endpoints_require_device_token():
    app = FastAPI()
    app.include_router(router.agent_router)
    resp = TestClient(app).post("/api/ordernmc-mirror/v1/agent/pull")
    assert resp.status_code == 401


# ---- push ------------------------------------------------------------------

class _RecCur:
    def __init__(self):
        self.calls, self.rowcount = [], 3

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class _RecConn:
    def __init__(self):
        self.cur = _RecCur()
        self.committed = False

    def cursor(self):
        return self.cur

    def commit(self):
        self.committed = True


def test_mark_due_keeps_ledger_and_running_passes():
    conn = _RecConn()
    assert repository.mark_due(conn, 1, [5, 9]) == 3 and conn.committed
    sql, params = conn.cur.calls[0]
    assert sql.startswith("UPDATE nexora_mirror.table_state SET last_pass_completed_at = NULL")
    assert "pass_started_at IS NULL" in sql and "ledger" not in sql
    assert params == [1, 5, 9]


def test_push_for_store_only_targets_carrying_it(monkeypatch):
    targets = [
        {"target_id": 1, "is_enabled": True, "stores": "SMG,SMF"},
        {"target_id": 2, "is_enabled": True, "stores": "SMA"},
        {"target_id": 3, "is_enabled": True, "stores": None},      # unscoped: carries all
        {"target_id": 4, "is_enabled": False, "stores": "SMF"},
    ]
    monkeypatch.setattr(service.repo, "list_targets", lambda: targets)
    monkeypatch.setattr(service, "push", lambda tid, tables=None: {"target_id": tid})
    assert [p["target_id"] for p in service.push_for_store("smf")] == [1, 3]
