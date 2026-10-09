"""Orchestration for the Remote Order Agent contract.

Reuses ``modules.nmv_integration`` for the actual OrderNMC data layer (order
reads, result apply, one-time enrollment codes, connections) and adds only the
agent-contract behaviour: device register (token + derived secret), the
pending-order / version / ack lifecycle, and the result-push dedup ledger.
"""
from __future__ import annotations

import datetime

from modules.nmv_integration import audit_service, enrollment
from modules.nmv_integration import repository as nmv_repo
from modules.nmv_integration import sync_service
from modules.remote_order_agent import repository, security
from modules.remote_order_agent.exceptions import AgentContractError

ORDER_VERSION_DEFAULT = 1
_ACK_TERMINAL = ("APPLIED", "REJECTED")
_ACK_STATES = ("APPLIED", "REJECTED", "DEFERRED")

# after-value key (agent wire) -> apply_order_result key
_RESULT_KEY_MAP = {
    "order_qty": "order_qty",
    "or_qty": "or_qty",
    "qtycheck": "qty_check",
    "remarks": "remarks",
    "or_supplier": "or_supplier",
    "or_supplier_code": "or_supplier_code",
    "status": "status",
}


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _iso(value):
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    return value


def _ci(row):
    return {str(k).lower(): v for k, v in row.items()}


def _to_int(value, default=0):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            value = value.strip()
            return int(float(value)) if value else default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _status_int(raw):
    """OrderManagement.Status is nvarchar '0'|'1'|'2'; the wire wants 0 (open) or
    2 (excluded). '1' (assigned) is delivered as 0 so agent line validation
    (status in {0,2}) passes -- the device re-derives supplier assignment."""
    return 2 if (raw is not None and str(raw).strip() == "2") else 0


# ---- store resolution -----------------------------------------------------

def resolve_store(store_code):
    store = nmv_repo.resolve_platform_store(store_code)
    if not store:
        raise AgentContractError("WRONG_STORE", "Unknown store", http_status=404)
    if not store.get("is_active", True):
        raise AgentContractError("WRONG_STORE", "Store is inactive", http_status=403)
    return store


# ---- 1. register ----------------------------------------------------------

def register(body):
    store = resolve_store(body.store_code)
    if body.store_id and str(body.store_id).lower() != str(store["store_id"]).lower():
        raise AgentContractError("WRONG_STORE", "store_id does not match store_code", http_status=403)

    nmv_repo.ensure_enrollment_schema()
    outcome = nmv_repo.redeem_enrollment_code(
        enrollment._hash_code(body.enrollment_code),
        store["store_id"], enrollment.MAX_ENROLL_ATTEMPTS,
    )
    if outcome["status"] != "ok":
        status = outcome["status"]
        audit_service.record("nmv.agent.register", store["store_code"], ok=False, error=status)
        if status == "locked":
            raise AgentContractError("RATE_LIMITED", "Too many attempts; request a new code.", http_status=429)
        raise AgentContractError("INVALID_CODE", "Invalid or expired enrollment code.", http_status=403)

    code = outcome["code"]
    repository.ensure_device_schema()
    token = security.new_device_token()
    device_id = repository.create_device(
        store, security.hash_token(token), body.machine_name, body.agent_version
    )
    secret = security.derive_device_secret(device_id)
    try:
        nmv_repo.attach_device_to_code(code["id"], device_id)
    except Exception:
        pass  # audit linkage only; the code is already consumed

    audit_service.record(
        "nmv.agent.register", store["store_code"], device_id, target_id=code.get("id"),
        metadata={"machine_name": body.machine_name, "agent_version": body.agent_version},
    )
    return security.envelope(
        store, device_id=device_id, device_token=token, device_secret=secret,
    )


# ---- 2. heartbeat ---------------------------------------------------------

def heartbeat(store, device, body):
    repository.ensure_device_schema()
    payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    repository.touch_device(device["device_id"], heartbeat=payload, agent_version=body.agent_version)
    return security.envelope(store, server_time=_now_iso())


# ---- 3. orders/pending ----------------------------------------------------

def orders_pending(store, limit=5):
    repository.ensure_order_schema()
    store_name = store["order_store_name"]
    conn = nmv_repo._central()
    try:
        cur = conn.cursor()
        order_id = nmv_repo.current_order_id(cur, store_name)
        if order_id is None:
            return security.envelope(store, orders=[])
        ack = repository.get_order_ack(cur, store_name, order_id, ORDER_VERSION_DEFAULT)
        if ack and ack["state"] in _ACK_TERMINAL:
            return security.envelope(store, orders=[])  # already delivered
        rows = sync_service.read_order(cur, store_name, order_id)
        header = repository.read_order_header(cur, store_name, order_id)
    finally:
        conn.close()

    if not rows:
        return security.envelope(store, orders=[])
    order = _build_order(store, order_id, rows, header)
    return security.envelope(store, orders=[order])


def _build_order(store, order_id, rows, header):
    lines = [_map_line(r) for r in rows]
    header = header or {}
    return {
        "order_id": int(order_id),
        "version": ORDER_VERSION_DEFAULT,
        "store_code": store["store_code"],
        "order_no": header.get("order_no"),
        "order_datetime": _iso(header.get("order_datetime")),
        "min_days": header.get("min_days"),
        "max_days": header.get("max_days"),
        "last_sale_bill_no": header.get("last_sale_bill_no"),
        "last_bill_datetime": _iso(header.get("last_bill_datetime")),
        "last_grn": header.get("last_grn"),
        "line_count": len(lines),
        "lines_sha256": compute_lines_sha256(lines),
        "lines": lines,
    }


def _map_line(row):
    r = _ci(row)
    order_qty = _to_int(r.get("orderqty"))
    product_type = _to_int(r.get("producttype"))
    name = r.get("producttypename")
    product_type_name = (str(name).strip() if name and str(name).strip()
                         else ("Pharma" if product_type == 1 else "Non Pharma"))
    return {
        "product_code": _to_int(r.get("productcode")),
        "product_name": r.get("productname"),
        "total_stock": r.get("totalstock"),
        "sale_unit": r.get("saleunit"),
        "purchase_price": r.get("purchaseprice"),
        "mrp": r.get("mrp"),
        "sub_location": r.get("sublocation"),
        "unit_description": r.get("unitdescription"),
        "last_received_date": _iso(r.get("lastreceiveddate")),
        "last_sale_date": _iso(r.get("lastsaledate")),
        "transaction_date": _iso(r.get("transactiondate")),
        "sls_qty": r.get("slsqty"),
        "max_sale_qty": r.get("maxsaleqty"),
        "wanted_date": _iso(r.get("wanteddate")),
        "wanted_type": r.get("wantedtype"),
        "status": _status_int(r.get("status")),
        "order_qty": order_qty,
        "org_order_qty": _to_int(r.get("orgorderqty"), default=order_qty),
        "product_type": product_type,
        "product_type_name": product_type_name,
        "min_qty": r.get("minqty"),
        "max_qty": r.get("maxqty"),
        "frequence": r.get("frequence"),
        "remarks": r.get("remarks"),
    }


def compute_lines_sha256(lines):
    """Exactly the agent's rule (docs/02 sec 3): lines sorted by product_code
    asc; each canonicalised as product_code|order_qty|org_order_qty|status|
    product_type (base-10 ints); joined by '\\n'; sha256 lowercase hex."""
    canon = "\n".join(
        "{0}|{1}|{2}|{3}|{4}".format(
            int(ln["product_code"]), int(ln["order_qty"]), int(ln["org_order_qty"]),
            int(ln["status"]), int(ln["product_type"]),
        )
        for ln in sorted(lines, key=lambda x: int(x["product_code"]))
    )
    return security.sha256_hex(canon.encode("utf-8"))


# ---- 3b. order ack --------------------------------------------------------

def order_ack(store, order_id, body):
    state = str(body.state or "").upper()
    if state not in _ACK_STATES:
        raise AgentContractError("INVALID_LINE", f"Unknown ack state '{body.state}'.")
    repository.ensure_order_schema()
    store_name = store["order_store_name"]
    conn = nmv_repo._central()
    try:
        cur = conn.cursor()
        repository.set_order_ack(
            cur, store_name, order_id, body.version, state,
            payload_sha256=body.payload_sha256,
            applied_line_count=body.applied_line_count,
            reason_code=body.reason_code, reason=body.reason,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    audit_service.record(
        "nmv.agent.order_ack", store["store_code"],
        target_id=str(order_id), ok=(state != "REJECTED"),
        metadata={"order_id": order_id, "version": body.version, "state": state,
                  "reason_code": body.reason_code},
    )
    return security.envelope(store, order_id=order_id, version=body.version, state=state)


# ---- 4. order results -----------------------------------------------------

def order_results(store, device, body):
    repository.ensure_order_schema()
    store_name = store["order_store_name"]
    store_id = store["store_id"]
    accepted, duplicates, rejected = [], [], []

    conn = nmv_repo._central()
    try:
        cur = conn.cursor()
        for item in body.items:
            cid = item.change_id
            if repository.result_already_applied(cur, store_id, body.queue_epoch, cid):
                duplicates.append(cid)
                continue
            try:
                applied = _apply_one_result(cur, store_name, item)
            except AgentContractError as exc:
                rejected.append({"change_id": cid, "code": exc.code,
                                 "message": exc.message, "retryable": exc.retryable})
                continue
            if applied:
                repository.record_result(cur, store_id, body.queue_epoch, cid,
                                         item.operation, item.order_id, item.product_code)
                accepted.append(cid)
            else:
                rejected.append({"change_id": cid, "code": "UNKNOWN_ORDER",
                                 "message": "order line not found on HO", "retryable": False})
        conn.commit()
    except AgentContractError:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    audit_service.record(
        "nmv.agent.order_results", store["store_code"], device.get("device_id"),
        metadata={"batch_id": body.batch_id, "accepted": len(accepted),
                  "duplicates": len(duplicates), "rejected": len(rejected)},
    )
    return security.envelope(
        store, batch_id=body.batch_id,
        items_sha256=(body.items_sha256 or _items_sha256([i.change_id for i in body.items])),
        accepted=accepted, duplicates=duplicates, rejected=rejected,
    )


def _apply_one_result(cur, store_name, item):
    """Apply one result item. Returns True if it affected OrderNMC, False if the
    target order line was not found (so the caller rejects it)."""
    op = (item.operation or "U").upper()
    if op == "D":
        repository.delete_order_line(cur, store_name, item.order_id, item.product_code)
        return True  # idempotent: already-gone counts as applied
    after = item.after or {}
    mapped = {"product_code": item.product_code}
    for wire_key, apply_key in _RESULT_KEY_MAP.items():
        if after.get(wire_key) is not None:
            mapped[apply_key] = after.get(wire_key)
    if len(mapped) == 1:  # only product_code -> nothing to write
        return True
    outcome = nmv_repo.apply_order_result(cur, store_name, item.order_id, mapped)
    return outcome == "applied"


def _items_sha256(change_ids):
    joined = ",".join(str(c) for c in sorted(change_ids))
    return security.sha256_hex(joined.encode("utf-8"))
