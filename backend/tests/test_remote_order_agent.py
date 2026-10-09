"""Offline tests for the Remote Order Agent contract (/api/nmv/v1).

No live DB: platform device state is an in-memory dict and the OrderNMC cursor is
a programmable fake. Covers the end-to-end HTTP path (register over the public
allow-list, then an HMAC-signed pull), the order->line mapping + lines_sha256
rule, the ack lifecycle, and result-push apply/dedup/reject.
"""
from __future__ import annotations

import datetime
import hashlib
import time

import pytest

from modules.nmv_integration import audit_service
from modules.nmv_integration import repository as nmv_repo
from modules.remote_order_agent import repository as roa_repo
from modules.remote_order_agent import security, service
from modules.remote_order_agent.exceptions import AgentContractError
from modules.remote_order_agent.schemas import (
    OrderAckRequest,
    OrderResultItem,
    OrderResultsRequest,
    RegisterRequest,
)

STORE = {
    "store_id": "4a2ceff0-13c5-484c-b263-de297e1e23e3",
    "tenant_id": "a7eb45bd-bdd7-4ee6-bd7b-61d1c7f4305d",
    "store_code": "NMV",
    "store_name": "NMV",
    "is_active": True,
    "order_store_name": "NMV",
}

ORDER_ID = 202610081200001

# (ProductCode, ProductName, TotalStock, SaleUnit, PurchasePrice, MRP, SubLocation,
#  UnitDescription, SLSQty, WantedType, Status, MaxSaleQty, OrderQty, OrgOrderQty,
#  ProductType, ProductTypeName, Remarks, OrderId, StoreName, StoreCode)
ORDER_COLS = [
    "ProductCode", "ProductName", "TotalStock", "SaleUnit", "PurchasePrice", "MRP",
    "SubLocation", "UnitDescription", "SLSQty", "WantedType", "Status", "MaxSaleQty",
    "OrderQty", "OrgOrderQty", "ProductType", "ProductTypeName", "Remarks",
    "OrderId", "StoreName", "StoreCode",
]
ORDER_ROWS = [
    (10234, "PARA 500", 4.0, 10.0, 12.5, 18.0, "A1", "10 TAB", 120.0, "Regular",
     "0", 10.0, 3.0, 3.0, 1.0, "Pharma", None, ORDER_ID, "NMV", 10.0),
    (10050, "COUGH SYP", 2.0, 1.0, 40.0, 60.0, "B2", "1 BTL", 30.0, "Regular",
     "2", 5.0, 1.0, 1.0, 0.0, "Non Pharma", "Additional", ORDER_ID, "NMV", 10.0),
]
HEADER_ROW = ("NMV", ORDER_ID, 1, datetime.datetime(2026, 10, 8, 12, 0, 0),
              "C12345", None, 98765, 15, 20)


class FakeCursor:
    def __init__(self):
        self.max_order_id = ORDER_ID
        self.ack_row = None
        self.header_row = HEADER_ROW
        self.ledger_present = set()
        self.update_rowcounts = []
        self.rowcount = 0
        self.description = None
        self._one = None
        self._all = None
        self.executed = []

    def execute(self, sql, *params):
        self.executed.append((sql, params))
        u = " ".join(sql.split()).upper()
        self._one = None
        self._all = None
        if "MAX(ORDERID)" in u:
            self._one = (self.max_order_id,)
        elif "FROM DBO.NMV_ORDER_ACK" in u and "MERGE" not in u:
            self._one = self.ack_row
        elif u.startswith("SELECT * FROM ORDERMANAGEMENT"):
            self.description = [(c,) for c in ORDER_COLS]
            self._all = list(ORDER_ROWS)
        elif "FROM ORDERHEADERDETAILS" in u:
            self._one = self.header_row
        elif "FROM DBO.NMV_AGENT_RESULT_LEDGER" in u:
            cid = params[2] if len(params) >= 3 else None
            self._one = (1,) if cid in self.ledger_present else None
        elif u.startswith("UPDATE ORDERMANAGEMENT"):
            self.rowcount = self.update_rowcounts.pop(0) if self.update_rowcounts else 1
        elif u.startswith("DELETE FROM ORDERMANAGEMENT"):
            self.rowcount = 1
        return self

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all or []


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


@pytest.fixture
def patched(monkeypatch):
    """No-op the schema/audit/platform side; return the central FakeCursor so a
    test can program it."""
    cur = FakeCursor()
    conn = FakeConn(cur)
    monkeypatch.setattr(roa_repo, "ensure_device_schema", lambda: None)
    monkeypatch.setattr(roa_repo, "ensure_order_schema", lambda: None)
    monkeypatch.setattr(nmv_repo, "ensure_enrollment_schema", lambda: None)
    monkeypatch.setattr(nmv_repo, "_central", lambda: conn)
    monkeypatch.setattr(nmv_repo, "resolve_platform_store",
                        lambda code: STORE if str(code) == "NMV" else None)
    monkeypatch.setattr(nmv_repo, "attach_device_to_code", lambda *a, **k: None)
    monkeypatch.setattr(audit_service, "record", lambda *a, **k: None)
    return cur


# ---- lines_sha256 pinned to the documented rule ---------------------------

def _expected_hash(lines):
    canon = "\n".join(
        "{0}|{1}|{2}|{3}|{4}".format(
            int(l["product_code"]), int(l["order_qty"]), int(l["org_order_qty"]),
            int(l["status"]), int(l["product_type"]))
        for l in sorted(lines, key=lambda x: int(x["product_code"])))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def test_orders_pending_maps_lines_and_hash(patched):
    resp = service.orders_pending(STORE, limit=5)
    assert resp["ok"] and resp["store_code"] == "NMV"
    assert len(resp["orders"]) == 1
    order = resp["orders"][0]
    assert order["order_id"] == ORDER_ID
    assert order["line_count"] == 2
    assert order["order_no"] == 1 and order["last_sale_bill_no"] == "C12345"
    # status '1'->0 / '2'->2 mapping + product_type_name defaulting
    by_code = {l["product_code"]: l for l in order["lines"]}
    assert by_code[10234]["status"] == 0 and by_code[10234]["product_type_name"] == "Pharma"
    assert by_code[10050]["status"] == 2 and by_code[10050]["order_qty"] == 1
    # hash matches the documented canonicalisation exactly
    assert order["lines_sha256"] == _expected_hash(order["lines"])
    assert order["lines_sha256"] == service.compute_lines_sha256(order["lines"])


def test_orders_pending_empty_when_already_applied(patched):
    patched.ack_row = ("APPLIED", "abc", 2)
    resp = service.orders_pending(STORE, limit=5)
    assert resp["orders"] == []


def test_orders_pending_empty_when_no_order(patched):
    patched.max_order_id = None
    resp = service.orders_pending(STORE, limit=5)
    assert resp["orders"] == []


# ---- ack ------------------------------------------------------------------

def test_order_ack_roundtrip(patched):
    body = OrderAckRequest(order_id=ORDER_ID, version=1, state="APPLIED",
                           payload_sha256="x", applied_line_count=2)
    resp = service.order_ack(STORE, ORDER_ID, body)
    assert resp["ok"] and resp["state"] == "APPLIED" and resp["order_id"] == ORDER_ID


def test_order_ack_rejects_bad_state(patched):
    body = OrderAckRequest(order_id=ORDER_ID, state="BOGUS")
    with pytest.raises(AgentContractError) as ei:
        service.order_ack(STORE, ORDER_ID, body)
    assert ei.value.code == "INVALID_LINE"


# ---- result push: apply / dedup / reject ----------------------------------

def test_order_results_apply_dedup_reject(patched):
    patched.ledger_present = {5050}          # change 5050 already applied
    patched.update_rowcounts = [1, 0]        # 1001 applies, 1002 misses
    items = [
        OrderResultItem(change_id=1001, operation="U", order_id=ORDER_ID,
                        product_code=10234, after={"order_qty": 5, "qtycheck": 1}),
        OrderResultItem(change_id=5050, operation="U", order_id=ORDER_ID,
                        product_code=10234, after={"order_qty": 9}),
        OrderResultItem(change_id=1002, operation="U", order_id=ORDER_ID,
                        product_code=99999, after={"order_qty": 2}),
    ]
    body = OrderResultsRequest(batch_id="b-1", queue_epoch="epoch-1",
                               count=3, items=items)
    device = {"device_id": "dev-1"}
    resp = service.order_results(STORE, device, body)
    assert resp["ok"] and resp["batch_id"] == "b-1"
    assert resp["accepted"] == [1001]
    assert resp["duplicates"] == [5050]
    assert len(resp["rejected"]) == 1 and resp["rejected"][0]["change_id"] == 1002
    assert resp["rejected"][0]["code"] == "UNKNOWN_ORDER"


# ---- register (service level) ---------------------------------------------

def test_register_bad_code_raises(patched, monkeypatch):
    monkeypatch.setattr(nmv_repo, "redeem_enrollment_code",
                        lambda h, sid, maxa: {"status": "expired", "code": {}})
    body = RegisterRequest(store_code="NMV", store_id=STORE["store_id"],
                           enrollment_code="BAD")
    with pytest.raises(AgentContractError) as ei:
        service.register(body)
    assert ei.value.code == "INVALID_CODE" and ei.value.http_status == 403


def test_register_ok_returns_token_and_derived_secret(patched, monkeypatch):
    monkeypatch.setattr(nmv_repo, "redeem_enrollment_code",
                        lambda h, sid, maxa: {"status": "ok",
                                              "code": {"id": "code-1"}})
    monkeypatch.setattr(roa_repo, "create_device",
                        lambda store, th, machine_name=None, agent_version=None: "dev-xyz")
    body = RegisterRequest(store_code="NMV", store_id=STORE["store_id"],
                           enrollment_code="GOOD", machine_name="DESKTOP-2")
    resp = service.register(body)
    assert resp["ok"] and resp["device_id"] == "dev-xyz"
    assert resp["device_token"] and resp["device_secret"]
    # secret is the deterministic derivation of the device_id
    assert resp["device_secret"] == security.derive_device_secret("dev-xyz")


# ---- HMAC signature helper ------------------------------------------------

def test_signature_roundtrip_and_skew():
    secret = security.derive_device_secret("dev-1")
    ts = str(int(time.time()))
    canon = security.build_canonical(ts, "GET", "/api/nmv/v1/orders/pending?limit=5", b"")
    sig = security.hmac_sha256_hex(secret, canon)
    ok, _ = security.verify_signature("dev-1", ts, "GET",
                                      "/api/nmv/v1/orders/pending?limit=5", b"", sig)
    assert ok
    bad, reason = security.verify_signature(
        "dev-1", str(int(ts) - 10_000), "GET",
        "/api/nmv/v1/orders/pending?limit=5", b"", sig)
    assert not bad and reason == "timestamp skew"


# ---- full HTTP path: public register + HMAC-signed pull -------------------

def test_http_register_then_signed_pull(patched, monkeypatch):
    from fastapi.testclient import TestClient
    from api.app import app

    devices = {}

    def fake_create_device(store, token_hash, machine_name=None, agent_version=None):
        did = "dev-" + token_hash[:10]
        devices[token_hash] = {
            "device_id": did, "store_id": store["store_id"],
            "store_code": store["store_code"], "status": "active",
            "machine_name": machine_name, "agent_version": agent_version,
        }
        return did

    monkeypatch.setattr(roa_repo, "create_device", fake_create_device)
    monkeypatch.setattr(roa_repo, "get_device_by_token_hash", lambda th: devices.get(th))
    monkeypatch.setattr(roa_repo, "touch_device", lambda *a, **k: None)
    monkeypatch.setattr(nmv_repo, "redeem_enrollment_code",
                        lambda h, sid, maxa: {"status": "ok", "code": {"id": "code-1"}})

    client = TestClient(app)

    # 1) register over the unauthenticated, allow-listed route
    reg = client.post("/api/nmv/v1/agent/register", json={
        "store_code": "NMV", "store_id": STORE["store_id"],
        "enrollment_code": "K7Q2-9ZB4", "machine_name": "DESKTOP-2",
        "agent_version": "1.0.0"})
    assert reg.status_code == 200, reg.text
    body = reg.json()
    assert body["ok"] and body["store_code"] == "NMV"
    token, secret = body["device_token"], body["device_secret"]

    # 2) HMAC-signed pull (exercises the allow-list + authenticate_device)
    path_and_query = "/api/nmv/v1/orders/pending?limit=5"
    ts = str(int(time.time()))
    canonical = security.build_canonical(ts, "GET", path_and_query, b"")
    sig = security.hmac_sha256_hex(secret, canonical)
    resp = client.get(path_and_query, headers={
        "Authorization": "Bearer " + token,
        "X-Nexora-Store-Id": STORE["store_id"],
        "X-Nexora-Store-Code": "NMV",
        "X-Nexora-Timestamp": ts,
        "X-Nexora-Signature": sig,
    })
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["ok"] and out["store_code"] == "NMV"
    assert out["orders"][0]["order_id"] == ORDER_ID

    # 3) a bad signature is rejected
    bad = client.get(path_and_query, headers={
        "Authorization": "Bearer " + token,
        "X-Nexora-Store-Id": STORE["store_id"],
        "X-Nexora-Store-Code": "NMV",
        "X-Nexora-Timestamp": ts,
        "X-Nexora-Signature": "deadbeef",
    })
    assert bad.status_code == 401


# ---- HO-side: NMV user access to their own order details ------------------

class _FakeReq:
    def __init__(self, method, path, path_params):
        self.method = method
        self.url = type("U", (), {"path": path})()
        self.path_params = path_params


def test_legacy_order_console_access_matrix():
    """The NMV purchase manager may GET their own store's read-only order views
    but nothing else; admins keep the full console."""
    from fastapi import HTTPException
    from modules.legacy_order.router import require_order_console_access

    admin = {"is_platform_user": True}
    nmv = {"store_code": "NMV", "is_platform_user": False, "role_names": ["PURCHASE_MANAGER"]}

    # admin: anything, including a destructive POST
    assert require_order_console_access(
        _FakeReq("POST", "/api/legacy-order/db/recover", {}), admin) is admin

    # NMV user: own-store order + qty-check detail reads are allowed
    assert require_order_console_access(
        _FakeReq("GET", "/api/legacy-order/orders/NMV", {"store_name": "NMV"}), nmv) is nmv
    assert require_order_console_access(
        _FakeReq("GET", "/api/legacy-order/qty-check/NMV/123/sales-details",
                 {"store_name": "NMV", "product_code": "123"}), nmv) is nmv

    # another store's data -> 403
    with pytest.raises(HTTPException) as e1:
        require_order_console_access(
            _FakeReq("GET", "/api/legacy-order/orders/NMA", {"store_name": "NMA"}), nmv)
    assert e1.value.status_code == 403

    # a mutating POST on their own store -> 403 (ops stays admin-only)
    with pytest.raises(HTTPException) as e2:
        require_order_console_access(
            _FakeReq("POST", "/api/legacy-order/orders/NMV/export", {"store_name": "NMV"}), nmv)
    assert e2.value.status_code == 403

    # an admin-only non-viewer read (store list) -> 403
    with pytest.raises(HTTPException) as e3:
        require_order_console_access(
            _FakeReq("GET", "/api/legacy-order/stores", {}), nmv)
    assert e3.value.status_code == 403
