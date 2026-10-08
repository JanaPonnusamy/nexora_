"""Orchestration for the NMV boundary -- the only layer the router calls.

Inbound writes (uplink, order-results) run in a single OrderNMC transaction that
commits the idempotency ledger row together with the data, so a retry after a
successful commit returns the stored response and applies nothing twice. Reads
are StoreName-scoped and never return another store's rows.
"""
from __future__ import annotations

import datetime
import os
import uuid

from modules.nmv_integration import (
    audit_service,
    idempotency,
    repository,
    sync_service,
)
from modules.nmv_integration.exceptions import MalformedPayload

CONFIG_VERSION = 1
POLL_INTERVAL_SECONDS = int(os.getenv("NMV_POLL_INTERVAL_SECONDS", "60"))
MAX_ROWS_PER_PAGE = int(os.getenv("NMV_MAX_ROWS_PER_PAGE", "2000"))


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _valid_guid(value):
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _require_message_id(message_id):
    if not _valid_guid(message_id):
        raise MalformedPayload("message_id must be a UUID.")


def _split_watermark(watermark):
    """(numeric, string) split for the two-column watermark store."""
    if watermark is None:
        return None, None
    if isinstance(watermark, bool):
        return None, str(watermark)
    if isinstance(watermark, int):
        return watermark, None
    text = str(watermark).strip()
    if text.lstrip("-").isdigit():
        return int(text), None
    return None, text


# ---- reads ----------------------------------------------------------------

def get_config(store):
    return {
        "store_code": store["store_code"],
        "config_version": CONFIG_VERSION,
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
        "max_rows_per_page": MAX_ROWS_PER_PAGE,
        "server_time": _now_iso(),
    }


def get_manifest(store):
    repository.ensure_schema()
    store_name = store["order_store_name"]
    stored = {w["entity"]: w for w in repository.list_watermarks(store_name)}

    conn = repository._central()
    try:
        current_order_id = repository.current_order_id(conn.cursor(), store_name)
    finally:
        conn.close()

    uplink = [
        {
            "entity": table,
            "strategy": strategy,
            "watermark": stored.get(table, {}).get("watermark"),
        }
        for table, strategy in sync_service.UPLINK_STRATEGY.items()
    ]
    downlink = [
        {
            "entity": entity,
            "strategy": "order_id" if entity.startswith("Order") else "content_hash",
            "watermark": stored.get(entity, {}).get("watermark"),
        }
        for entity in sync_service.downlink_entities()
    ]
    return {
        "store_code": store["store_code"],
        "store_name": store["store_name"],
        "config_version": CONFIG_VERSION,
        "current_order_id": current_order_id,
        "uplink": uplink,
        "downlink": downlink,
        "server_time": _now_iso(),
    }


def get_changes(store, entity, cursor, limit):
    store_name = store["order_store_name"]
    limit = min(int(limit or MAX_ROWS_PER_PAGE), MAX_ROWS_PER_PAGE)
    conn = repository._central()
    try:
        rows, next_cursor, has_more = sync_service.read_entity_page(
            conn.cursor(), store_name, entity, cursor, limit
        )
    finally:
        conn.close()
    return {
        "entity": entity,
        "rows": rows,
        "next_cursor": next_cursor,
        "watermark": next_cursor,
        "has_more": has_more,
    }


def get_orders(store, order_id):
    store_name = store["order_store_name"]
    conn = repository._central()
    try:
        cur = conn.cursor()
        resolved = order_id if order_id is not None else repository.current_order_id(cur, store_name)
        rows = sync_service.read_order(cur, store_name, resolved) if resolved is not None else []
    finally:
        conn.close()
    return {"store_code": store["store_code"], "order_id": resolved, "rows": rows}


def get_status(store):
    repository.ensure_schema()
    store_name = store["order_store_name"]
    return {
        "store_code": store["store_code"],
        "store_name": store["store_name"],
        "watermarks": repository.list_watermarks(store_name),
        "recent": repository.recent_audit(store_name),
    }


# ---- writes (idempotent, transactional) -----------------------------------

def ingest_uplink(store, device_id, req):
    _require_message_id(req.message_id)
    repository.ensure_schema()
    store_name = store["order_store_name"]

    conn = repository._central()
    try:
        cur = conn.cursor()
        duplicate = idempotency.already_applied(cur, req.message_id)
        if duplicate is not None:
            conn.rollback()
            duplicate = dict(duplicate)
            duplicate["skipped_duplicate"] = True
            return duplicate

        try:
            repository.insert_message(cur, req.message_id, store_name, "up", "uplink", len(req.rows))
        except Exception as exc:  # concurrent duplicate committed between the two steps
            conn.rollback()
            if idempotency.is_duplicate_insert(exc):
                stored = idempotency.already_applied(conn.cursor(), req.message_id) or {}
                conn.rollback()
                stored = dict(stored)
                stored["skipped_duplicate"] = True
                return stored
            raise

        rows_applied, dropped = sync_service.apply_uplink(
            cur, req.table, req.columns, req.rows, store_name, req.snapshot_reset
        )
        if req.watermark is not None:
            strategy = sync_service.UPLINK_STRATEGY.get(req.table, "id")
            _advance_watermark(cur, store_name, req.table, strategy, req.watermark)

        errors = [f"ignored unknown column: {c}" for c in dropped]
        response = {
            "message_id": req.message_id,
            "table": req.table,
            "rows_in": len(req.rows),
            "rows_applied": rows_applied,
            "skipped_duplicate": False,
            "errors": errors,
            "watermark": req.watermark,
        }
        repository.complete_message(cur, req.message_id, "applied", rows_applied, response)
        repository.insert_audit(
            cur, store_name, device_id, req.message_id, req.table, "up", rows_applied,
            "ok", ("; ".join(errors) if errors else None),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    audit_service.record(
        "nmv.uplink", store["store_code"], device_id,
        metadata={"table": req.table, "rows_in": len(req.rows), "rows_applied": rows_applied},
    )
    return response


def ingest_order_results(store, device_id, req):
    _require_message_id(req.message_id)
    repository.ensure_schema()
    store_name = store["order_store_name"]

    conn = repository._central()
    try:
        cur = conn.cursor()
        duplicate = idempotency.already_applied(cur, req.message_id)
        if duplicate is not None:
            conn.rollback()
            duplicate = dict(duplicate)
            duplicate["skipped_duplicate"] = True
            return duplicate

        try:
            repository.insert_message(
                cur, req.message_id, store_name, "up", "order_results", len(req.results)
            )
        except Exception as exc:
            conn.rollback()
            if idempotency.is_duplicate_insert(exc):
                stored = idempotency.already_applied(conn.cursor(), req.message_id) or {}
                conn.rollback()
                stored = dict(stored)
                stored["skipped_duplicate"] = True
                return stored
            raise

        applied = 0
        conflicts = []
        for item in req.results:
            if hasattr(item, "model_dump"):      # pydantic v2
                payload = item.model_dump()
            elif hasattr(item, "dict"):          # pydantic v1
                payload = item.dict()
            else:
                payload = dict(item)
            outcome = repository.apply_order_result(cur, store_name, req.order_id, payload)
            if outcome == "applied":
                applied += 1
            elif outcome == "conflict":
                conflicts.append({"product_code": payload.get("product_code"), "reason": "status_changed"})
            else:
                conflicts.append({"product_code": payload.get("product_code"), "reason": "not_found"})

        response = {
            "message_id": req.message_id,
            "order_id": req.order_id,
            "rows_in": len(req.results),
            "rows_applied": applied,
            "conflicts": conflicts,
            "skipped_duplicate": False,
        }
        repository.complete_message(cur, req.message_id, "applied", applied, response)
        repository.insert_audit(
            cur, store_name, device_id, req.message_id, "OrderManagement", "up", applied,
            "ok" if not conflicts else "partial",
            (f"{len(conflicts)} conflict(s)" if conflicts else None),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    audit_service.record(
        "nmv.order_results", store["store_code"], device_id,
        metadata={"order_id": req.order_id, "rows_applied": applied, "conflicts": len(conflicts)},
    )
    return response


def ack(store, entity, watermark):
    repository.ensure_schema()
    store_name = store["order_store_name"]
    strategy = "order_id" if entity.startswith("Order") else "content_hash"
    conn = repository._central()
    try:
        cur = conn.cursor()
        _advance_watermark(cur, store_name, entity, strategy, watermark)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"entity": entity, "watermark": watermark}


def _advance_watermark(cur, store_name, entity, strategy, watermark):
    """Store the watermark, monotonically for numeric strategies so an
    out-of-order message can never move a high-water mark backwards."""
    num, text = _split_watermark(watermark)
    if num is not None:
        current = repository.get_watermark(cur, store_name, entity)
        if current and current.get("watermark_num") is not None and current["watermark_num"] >= num:
            return
    repository.set_watermark(cur, store_name, entity, strategy, num, text)
