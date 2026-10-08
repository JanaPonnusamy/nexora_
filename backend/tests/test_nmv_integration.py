"""Offline tests for the NMV integration boundary.

No live database: a programmable fake cursor/connection drives the SQL paths so
the suite runs anywhere. Covers the areas the task enumerates: authentication,
store isolation, manifest, initial + incremental uplink, order delivery,
duplicate delivery/result upload (idempotency), retry, partial/conflict,
watermark recovery, invalid store, unauthorized device, malformed payload.
"""
from __future__ import annotations

import datetime
import json
import uuid

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from config.security import ALGORITHM, SECRET_KEY, create_access_token
from modules.nmv_integration import (
    idempotency,
    repository,
    router,
    serializer,
    service,
    sync_service,
)
from modules.nmv_integration.exceptions import MalformedPayload, UnknownEntity
from modules.nmv_integration.schemas import (
    OrderResultItem,
    OrderResultsRequest,
    UplinkRequest,
)

STORE = {
    "store_id": "aaaaaaaa-0000-0000-0000-000000000001",
    "tenant_id": "bbbbbbbb-0000-0000-0000-000000000001",
    "store_code": "NMV",
    "store_name": "Nathan Medicals V",
    "is_active": True,
    "order_store_name": "NMV",
}


# --------------------------------------------------------------------------
# Fake DB
# --------------------------------------------------------------------------

_INFO_SCHEMA_PRODUCTS = [
    ("ProductCode", "int", None, 10, 0),
    ("ProductName", "nvarchar", 200, None, None),
    ("StoreName", "nvarchar", 100, None, None),
    ("Sync", "int", None, 10, 0),
    ("SyncDateTime", "datetime", None, None, None),
]


class FakeCursor:
    def __init__(self):
        self.executed = []
        self.executemany_payloads = []
        self.rowcount = 0
        self.description = None
        self.fast_executemany = False
        # programmable responses
        self.message_row = None
        self.watermark_row = None
        self.max_order_id = None
        self.info_schema = _INFO_SCHEMA_PRODUCTS
        self.select_star_rows = []
        self.update_rowcounts = []
        self.exists_counts = []
        self._pending_one = None
        self._pending_all = None

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        s = sql
        self._pending_one = None
        self._pending_all = None
        if "FROM dbo.nmv_sync_message" in s:
            self._pending_one = self.message_row
        elif "FROM dbo.nmv_sync_watermark" in s and "MERGE" not in s:
            self._pending_one = self.watermark_row
        elif "MAX(OrderId)" in s:
            self._pending_one = (self.max_order_id,)
        elif "INFORMATION_SCHEMA.COLUMNS" in s:
            self._pending_all = list(self.info_schema)
        elif s.strip().upper().startswith("SELECT COUNT(1) FROM ORDERMANAGEMENT"):
            self._pending_one = (self.exists_counts.pop(0),) if self.exists_counts else (0,)
        elif s.strip().upper().startswith("UPDATE ORDERMANAGEMENT"):
            self.rowcount = self.update_rowcounts.pop(0) if self.update_rowcounts else 1
        elif s.strip().upper().startswith("SELECT * FROM"):
            cols = ["ProductCode", "OrderId", "StoreName", "OrderQty"]
            self.description = [(c,) for c in cols]
            self._pending_all = list(self.select_star_rows)
        return self

    def executemany(self, sql, seq):
        self.executed.append((sql, ()))
        self.executemany_payloads.extend(seq)

    def fetchone(self):
        return self._pending_one

    def fetchall(self):
        return self._pending_all or []

    # convenience: all SQL text that ran
    def sql_text(self):
        return "\n".join(s for s, _ in self.executed)


class FakeConn:
    def __init__(self, cursor=None):
        self._cursor = cursor or FakeCursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


@pytest.fixture
def no_schema(monkeypatch):
    monkeypatch.setattr(repository, "ensure_schema", lambda: None)


def _patch_central(monkeypatch, cursor):
    conn = FakeConn(cursor)
    monkeypatch.setattr(repository, "_central", lambda: conn)
    return conn


# --------------------------------------------------------------------------
# Serializer
# --------------------------------------------------------------------------

def test_serializer_jsonable_types():
    import decimal
    assert serializer.to_jsonable(decimal.Decimal("12.50")) == "12.50"
    assert serializer.to_jsonable(datetime.date(2026, 1, 2)) == "2026-01-02"
    assert serializer.to_jsonable(b"\x01\x02") == "0102"
    assert serializer.to_jsonable(None) is None
    assert serializer.to_jsonable(5) == 5


def test_serializer_coerce_inbound_dates_and_bits():
    assert serializer.coerce_inbound("2026-01-02", "date") == datetime.date(2026, 1, 2)
    assert isinstance(serializer.coerce_inbound("2026-01-02T03:04:05", "datetime"), datetime.datetime)
    assert serializer.coerce_inbound(True, "bit") == 1
    assert serializer.coerce_inbound("abc", "nvarchar") == "abc"
    assert serializer.coerce_inbound(None, "datetime") is None


# --------------------------------------------------------------------------
# Uplink merge reuse + stamping (initial/incremental sync)
# --------------------------------------------------------------------------

def test_uplink_maps_suppliers_to_ordersuppliers_and_rejects_unknown():
    assert sync_service.dest_table_for("Suppliers") == "OrderSuppliers"
    assert sync_service.dest_table_for("Products") == "Products"
    with pytest.raises(UnknownEntity):
        sync_service.dest_table_for("NotATable")


def test_apply_uplink_stages_stamps_and_merges():
    cur = FakeCursor()
    rows = [{"ProductCode": 10, "ProductName": "Paracetamol"}]
    applied, dropped = sync_service.apply_uplink(
        cur, "Products", ["ProductCode", "ProductName"], rows, "NMV"
    )
    assert applied == 1
    assert dropped == []
    sql = cur.sql_text()
    # staging created, merged into Products, dropped
    assert "CREATE TABLE [nmv_stage_" in sql
    assert "MERGE [Products]" in sql
    assert "DROP TABLE" in sql
    # the StoreName/Sync/SyncDateTime stamp columns rode along into the payload
    payload = cur.executemany_payloads[0]
    assert "NMV" in payload  # StoreName stamp
    assert payload[0] == 10 and payload[1] == "Paracetamol"


def test_apply_uplink_drops_unknown_columns():
    cur = FakeCursor()
    applied, dropped = sync_service.apply_uplink(
        cur, "Products", ["ProductCode", "Bogus"], [{"ProductCode": 1, "Bogus": "x"}], "NMV"
    )
    assert dropped == ["Bogus"]
    assert applied == 1


def test_apply_uplink_batches_snapshot_reset_zeroes_stock():
    cur = FakeCursor()
    cur.info_schema = [
        ("ProductCode", "int", None, 10, 0),
        ("BatchCode", "nvarchar", 50, None, None),
        ("Stock", "float", None, None, None),
        ("StoreName", "nvarchar", 100, None, None),
        ("Sync", "int", None, 10, 0),
        ("SyncDateTime", "datetime", None, None, None),
    ]
    sync_service.apply_uplink(
        cur, "Batches", ["ProductCode", "BatchCode", "Stock"],
        [{"ProductCode": 1, "BatchCode": "B1", "Stock": 5}], "NMV", snapshot_reset=True,
    )
    assert "UPDATE Batches SET Stock = 0 WHERE StoreName = ?" in cur.sql_text()


# --------------------------------------------------------------------------
# Order-result apply: identity key, whitelist, conflict vs missing
# --------------------------------------------------------------------------

def test_apply_order_result_scopes_to_store_order_product():
    cur = FakeCursor()
    cur.update_rowcounts = [1]
    outcome = repository.apply_order_result(
        cur, "NMV", 77, {"product_code": 10, "order_qty": 4, "status": 1}
    )
    assert outcome == "applied"
    update_sql = cur.executed[0][0]
    assert "UPDATE OrderManagement" in update_sql
    assert "StoreName = ? AND OrderId = ? AND ProductCode = ?" in update_sql
    # only whitelisted columns are set
    assert "[OrderQty] = ?" in update_sql and "[Status] = ?" in update_sql
    assert "ProductName" not in update_sql


def test_apply_order_result_conflict_on_expected_status_mismatch():
    cur = FakeCursor()
    cur.update_rowcounts = [0]   # nothing updated (guard failed)
    cur.exists_counts = [1]      # but the row exists
    outcome = repository.apply_order_result(
        cur, "NMV", 77, {"product_code": 10, "status": 2, "expected_status": 0}
    )
    assert outcome == "conflict"


def test_apply_order_result_missing_when_no_row():
    cur = FakeCursor()
    cur.update_rowcounts = [0]
    cur.exists_counts = [0]
    outcome = repository.apply_order_result(
        cur, "NMV", 77, {"product_code": 999, "status": 1, "expected_status": 0}
    )
    assert outcome == "missing"


def test_apply_order_result_ignores_non_whitelisted_keys():
    cur = FakeCursor()
    cur.update_rowcounts = [1]
    repository.apply_order_result(
        cur, "NMV", 77,
        {"product_code": 10, "order_qty": 1, "ProductName": "hack", "TotalStock": 0},
    )
    update_sql = cur.executed[0][0]
    assert "ProductName" not in update_sql
    assert "TotalStock" not in update_sql


# --------------------------------------------------------------------------
# Downlink reads are StoreName-scoped (store isolation at the query level)
# --------------------------------------------------------------------------

def test_read_order_is_store_scoped():
    cur = FakeCursor()
    cur.select_star_rows = [(10, 77, "NMV", 4)]
    rows = sync_service.read_order(cur, "NMV", 77)
    assert rows and rows[0]["StoreName"] == "NMV"
    assert "WHERE StoreName = ? AND OrderId = ?" in cur.executed[0][0]


def test_read_entity_page_scopes_and_rejects_unknown_entity():
    cur = FakeCursor()
    cur.select_star_rows = []
    rows, nxt, more = sync_service.read_entity_page(cur, "NMV", "OrderSuppliers", None, 10)
    assert "WHERE StoreName = ?" in cur.executed[0][0]
    assert more is False and nxt is None
    with pytest.raises(UnknownEntity):
        sync_service.read_entity_page(cur, "NMV", "SecretTable", None, 10)


def test_read_entity_page_pagination_cursor():
    cur = FakeCursor()
    # limit=2 but 3 rows returned (limit+1) => has_more, next cursor advances
    cur.select_star_rows = [(1, 1, "NMV", 1), (2, 1, "NMV", 1), (3, 1, "NMV", 1)]
    rows, nxt, more = sync_service.read_entity_page(cur, "NMV", "OrderManagement", "0", 2)
    assert len(rows) == 2 and more is True and nxt == "2"


# --------------------------------------------------------------------------
# Idempotency: duplicate uplink + duplicate result upload (= retry)
# --------------------------------------------------------------------------

def _uplink_req(mid):
    return UplinkRequest(
        message_id=mid, table="Products",
        columns=["ProductCode", "ProductName"],
        rows=[{"ProductCode": 10, "ProductName": "Paracetamol"}],
        watermark=10,
    )


def test_ingest_uplink_applies_then_commits(monkeypatch, no_schema):
    cur = FakeCursor()
    cur.message_row = None  # not seen before
    conn = _patch_central(monkeypatch, cur)
    mid = str(uuid.uuid4())

    resp = service.ingest_uplink(STORE, "dev-1", _uplink_req(mid))

    assert resp["skipped_duplicate"] is False
    assert resp["rows_applied"] == 1
    assert conn.commits == 1 and conn.rollbacks == 0
    # the idempotency ledger + audit rows were written
    sql = cur.sql_text()
    assert "INSERT INTO dbo.nmv_sync_message" in sql
    assert "UPDATE dbo.nmv_sync_message" in sql
    assert "INSERT INTO dbo.nmv_sync_audit" in sql


def test_ingest_uplink_duplicate_is_skipped(monkeypatch, no_schema):
    stored = {"message_id": "x", "table": "Products", "rows_in": 1,
              "rows_applied": 1, "skipped_duplicate": False, "errors": [], "watermark": 10}
    cur = FakeCursor()
    cur.message_row = ("x", "NMV", "up", "uplink", "applied", 1, 1, None, json.dumps(stored))
    conn = _patch_central(monkeypatch, cur)

    resp = service.ingest_uplink(STORE, "dev-1", _uplink_req(str(uuid.uuid4())))

    assert resp["skipped_duplicate"] is True
    assert resp["rows_applied"] == 1
    # nothing applied: no MERGE, no INSERT of a new message row, rolled back
    sql = cur.sql_text()
    assert "MERGE [Products]" not in sql
    assert "INSERT INTO dbo.nmv_sync_message" not in sql
    assert conn.commits == 0 and conn.rollbacks == 1


def test_ingest_order_results_applies_and_reports_conflicts(monkeypatch, no_schema):
    cur = FakeCursor()
    cur.message_row = None
    cur.update_rowcounts = [1, 0]  # first applies, second doesn't
    cur.exists_counts = [1]        # second row exists -> conflict
    conn = _patch_central(monkeypatch, cur)

    req = OrderResultsRequest(
        message_id=str(uuid.uuid4()), order_id=77,
        results=[
            OrderResultItem(product_code=10, order_qty=4, status=1),
            OrderResultItem(product_code=11, status=2, expected_status=0),
        ],
    )
    resp = service.ingest_order_results(STORE, "dev-1", req)
    assert resp["rows_applied"] == 1
    assert resp["conflicts"] == [{"product_code": 11, "reason": "status_changed"}]
    assert conn.commits == 1


def test_ingest_order_results_duplicate_is_skipped(monkeypatch, no_schema):
    stored = {"message_id": "x", "order_id": 77, "rows_in": 1, "rows_applied": 1,
              "conflicts": [], "skipped_duplicate": False}
    cur = FakeCursor()
    cur.message_row = ("x", "NMV", "up", "order_results", "applied", 1, 1, None, json.dumps(stored))
    conn = _patch_central(monkeypatch, cur)

    req = OrderResultsRequest(
        message_id=str(uuid.uuid4()), order_id=77,
        results=[OrderResultItem(product_code=10, order_qty=4, status=1)],
    )
    resp = service.ingest_order_results(STORE, "dev-1", req)
    assert resp["skipped_duplicate"] is True
    assert conn.commits == 0 and conn.rollbacks == 1
    assert "UPDATE OrderManagement" not in cur.sql_text()


def test_malformed_message_id_rejected(no_schema):
    with pytest.raises(MalformedPayload):
        service.ingest_uplink(STORE, "dev-1", _uplink_req("not-a-uuid"))


# --------------------------------------------------------------------------
# Watermark recovery (monotonic advance + ack)
# --------------------------------------------------------------------------

def test_advance_watermark_is_monotonic_for_numeric(monkeypatch):
    cur = FakeCursor()
    cur.watermark_row = ("id", 500, None)  # already at 500
    service._advance_watermark(cur, "NMV", "PurchaseTrans", "id", 400)  # older
    # no MERGE issued because 400 < 500
    assert "MERGE dbo.nmv_sync_watermark" not in cur.sql_text()

    cur2 = FakeCursor()
    cur2.watermark_row = ("id", 500, None)
    service._advance_watermark(cur2, "NMV", "PurchaseTrans", "id", 600)  # newer
    assert "MERGE dbo.nmv_sync_watermark" in cur2.sql_text()


def test_ack_sets_watermark(monkeypatch, no_schema):
    cur = FakeCursor()
    cur.watermark_row = None
    conn = _patch_central(monkeypatch, cur)
    resp = service.ack(STORE, "OrderManagement", 77)
    assert resp == {"entity": "OrderManagement", "watermark": 77}
    assert "MERGE dbo.nmv_sync_watermark" in cur.sql_text()
    assert conn.commits == 1


def test_split_watermark_forms():
    assert service._split_watermark(5) == (5, None)
    assert service._split_watermark("12") == (12, None)
    assert service._split_watermark("abc") == (None, "abc")
    assert service._split_watermark(None) == (None, None)


# --------------------------------------------------------------------------
# Authentication + store isolation (get_nmv_context)
# --------------------------------------------------------------------------

def _device_token(store_ids, device_id="dev-1", kind="device"):
    return create_access_token({
        "sub": device_id, "token_kind": kind, "device_id": device_id,
        "store_ids": store_ids, "tenant_ids": [STORE["tenant_id"]],
    })


def _creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _patch_auth(monkeypatch, device=None, store=STORE):
    monkeypatch.setattr(router.device_repo, "get_device",
                        lambda did: device if device is not None else {"status": "active"})
    monkeypatch.setattr(router.repository, "resolve_platform_store",
                        lambda code: store if (store and code == store["store_code"]) else None)


def test_auth_valid_device_assigned_store(monkeypatch):
    _patch_auth(monkeypatch, device={"status": "active"})
    token = _device_token([STORE["store_id"]])
    ctx = router.get_nmv_context("NMV", _creds(token))
    assert ctx["device_id"] == "dev-1"
    assert ctx["store"]["store_code"] == "NMV"


def test_auth_rejects_non_device_token(monkeypatch):
    _patch_auth(monkeypatch, device={"status": "active"})
    token = _device_token([STORE["store_id"]], kind="user")
    with pytest.raises(HTTPException) as e:
        router.get_nmv_context("NMV", _creds(token))
    assert e.value.status_code == 403


def test_auth_rejects_revoked_device(monkeypatch):
    _patch_auth(monkeypatch, device={"status": "revoked"})
    token = _device_token([STORE["store_id"]])
    with pytest.raises(HTTPException) as e:
        router.get_nmv_context("NMV", _creds(token))
    assert e.value.status_code == 403


def test_auth_unknown_store_is_404(monkeypatch):
    _patch_auth(monkeypatch, device={"status": "active"}, store=STORE)
    token = _device_token([STORE["store_id"]])
    with pytest.raises(HTTPException) as e:
        router.get_nmv_context("NMX", _creds(token))  # resolve returns None
    assert e.value.status_code == 404


def test_auth_device_not_assigned_to_store_is_403(monkeypatch):
    _patch_auth(monkeypatch, device={"status": "active"})
    token = _device_token(["some-other-store-guid"])  # NMV's id not in token
    with pytest.raises(HTTPException) as e:
        router.get_nmv_context("NMV", _creds(token))
    assert e.value.status_code == 403


def test_auth_missing_credentials_is_401():
    with pytest.raises(HTTPException) as e:
        router.get_nmv_context("NMV", None)
    assert e.value.status_code == 401


def test_auth_expired_token_is_401(monkeypatch):
    _patch_auth(monkeypatch, device={"status": "active"})
    expired = jwt.encode(
        {"token_kind": "device", "device_id": "dev-1", "store_ids": [STORE["store_id"]],
         "exp": datetime.datetime(2000, 1, 1)},
        SECRET_KEY, algorithm=ALGORITHM,
    )
    with pytest.raises(HTTPException) as e:
        router.get_nmv_context("NMV", _creds(expired))
    assert e.value.status_code == 401


def test_auth_garbage_token_is_401(monkeypatch):
    _patch_auth(monkeypatch, device={"status": "active"})
    with pytest.raises(HTTPException) as e:
        router.get_nmv_context("NMV", _creds("not.a.jwt"))
    assert e.value.status_code == 401


# --------------------------------------------------------------------------
# Idempotency helper unit behaviour
# --------------------------------------------------------------------------

def test_already_applied_parses_stored_response():
    cur = FakeCursor()
    cur.message_row = ("x", "NMV", "up", "uplink", "applied", 1, 1, None, '{"rows_applied": 1}')
    assert idempotency.already_applied(cur, "x") == {"rows_applied": 1}

    cur2 = FakeCursor()
    cur2.message_row = None
    assert idempotency.already_applied(cur2, "x") is None


def test_is_duplicate_insert_detects_pk_violation():
    assert idempotency.is_duplicate_insert(Exception("23000 Violation of PRIMARY KEY constraint"))
    assert not idempotency.is_duplicate_insert(Exception("some other error"))
