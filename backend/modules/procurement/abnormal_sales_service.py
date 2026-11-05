"""Abnormal bill-sale review (rulebook PRR-SALE-ABNORMAL / PRR-SALE-WARNING).

Lists flagged products for the Procurement screen (platform sync.*, one
refresh) and the Order Workspace (legacy OrderNMC, the store's open order),
and marks / unmarks a bill "do not consider in order". A mark is written to
BOTH databases -- the legacy order SQL reads OrderNMC, the decision engine
reads sync.* -- so either screen's decision reaches both engines. It only
changes the next calculation (next order process / next refresh); quantities
already on screen are not recomputed.
"""

from __future__ import annotations

import datetime
import logging
import threading
import time

from fastapi import HTTPException

from modules.legacy_order import database as legacy_database
from modules.procurement import abnormal_sales
from modules.procurement import abnormal_sales_repository as repo
from modules.procurement import vpl_repository
from modules.procurement.rules_resolution import REGISTRY

logger = logging.getLogger(__name__)


def _thresholds(tenant_id, store_id):
    """Effective multipliers for the store (registry override, else default)."""
    abnormal = abnormal_sales.ABNORMAL_MULTIPLIER
    warning = abnormal_sales.WARNING_MULTIPLIER
    if tenant_id and store_id:
        try:
            for row in REGISTRY.resolve(str(tenant_id), str(store_id))["rules"]:
                if row["rule_id"] == "PRR-SALE-ABNORMAL":
                    abnormal = float(row["value"])
                elif row["rule_id"] == "PRR-SALE-WARNING":
                    warning = float(row["value"])
        except Exception:  # registry is advisory here; defaults still apply
            logger.exception("Abnormal-sale thresholds: registry resolve failed")
    return abnormal, min(warning, abnormal)


def _since():
    return datetime.date.today() - datetime.timedelta(days=abnormal_sales.WINDOW_DAYS)


def _normalise(rows):
    return [
        {
            "product_code": str(r["product_code"]),
            "bill_no": str(r["bill_no"] or "").strip(),
            "bill_date": str(r["bill_date"])[:10],
            "qty": float(r["qty"] or 0),
            "dont_consider": bool(r["dont_consider"]),
        }
        for r in rows
    ]


def _result(found, customers, abnormal, warning):
    for summary in found.values():
        for bill in summary["bills"]:
            bill["customer"] = customers.get((bill["bill_no"], bill["bill_date"]))
    items = sorted(found.values(), key=lambda s: (s["level"] != "abnormal", -s["max_ratio"]))
    return {
        "abnormal_multiplier": abnormal,
        "warning_multiplier": warning,
        "window_days": abnormal_sales.WINDOW_DAYS,
        "items": items,
    }


def _flagged_bill_keys(found):
    return {(b["bill_no"], b["bill_date"]) for s in found.values() for b in s["bills"]}


def platform_abnormal_sales(tenant_id, refresh_id):
    refresh = vpl_repository.get_vpl(tenant_id, refresh_id)
    if not refresh:
        raise HTTPException(status_code=404, detail="Refresh not found")
    store_id = refresh.get("store_id")
    abnormal, warning = _thresholds(tenant_id, store_id)
    rows = _normalise(repo.platform_bills(tenant_id, refresh_id, _since()))
    found = abnormal_sales.classify_bills(rows, abnormal=abnormal, warning=warning)
    customers = repo.platform_customers(tenant_id, store_id, _flagged_bill_keys(found)) if store_id else {}
    return _result(found, customers, abnormal, warning)


# The legacy bill read costs ~8s alone on OrderNMC (one clustered-index
# lookup per sale line for Bnumber, random disk reads on SQL Express) and the
# Procurement screen re-asked after every export. Overlapping copies piled up
# to 100s+ each and starved the export / qty-check queries into timeouts and
# 1205 deadlocks (2026-11-02, NMS). One computation per store at a time, and
# a short cache shared by every client; a dont-consider mark clears it.
_LEGACY_CACHE_TTL = 300
_legacy_cache: dict[str, tuple[float, dict]] = {}
_legacy_locks: dict[str, threading.Lock] = {}
_legacy_locks_guard = threading.Lock()


def _legacy_key(store_name):
    return str(store_name or "").strip().upper()


def invalidate_legacy_cache(store_name):
    _legacy_cache.pop(_legacy_key(store_name), None)


def legacy_abnormal_sales(store_name):
    key = _legacy_key(store_name)
    with _legacy_locks_guard:
        lock = _legacy_locks.setdefault(key, threading.Lock())
    with lock:
        hit = _legacy_cache.get(key)
        if hit and time.monotonic() - hit[0] < _LEGACY_CACHE_TTL:
            return hit[1]
        result = _compute_legacy_abnormal_sales(store_name)
        _legacy_cache[key] = (time.monotonic(), result)
        return result


def _legacy_store(store_code):
    """The platform store behind a legacy OrderNMC store name. Tenant-aware: the
    same code can exist under two tenants (see legacy_database.platform_store_id)."""
    store_id = legacy_database.platform_store_id(store_code)
    return repo.store_by_id(store_id) if store_id else None


def _compute_legacy_abnormal_sales(store_name):
    store = _legacy_store(store_name)
    abnormal, warning = _thresholds(store and store["tenant_id"], store and store["store_id"])
    rows = _normalise(repo.legacy_bills(store_name, _since()))
    found = abnormal_sales.classify_bills(rows, abnormal=abnormal, warning=warning)
    customers = repo.legacy_customers(store_name, _flagged_bill_keys(found))
    return _result(found, customers, abnormal, warning)


def set_dont_consider(*, store_id=None, store_code=None, tenant_id=None, product_code, bill_no, bill_date, dont_consider):
    """Mark / unmark one product's lines on one bill in both databases.

    Pass the platform store_id (Procurement) or the legacy store_code (Order
    Workspace); the other is resolved from dbo.stores. Returns per-database
    row counts; a database that cannot be reached is reported, not raised,
    as long as the other one was updated.
    """
    store = repo.store_by_id(store_id) if store_id else _legacy_store(store_code)
    if store_id and (not store or (tenant_id and str(store["tenant_id"]).upper() != str(tenant_id).upper())):
        raise HTTPException(status_code=404, detail="Store not found")
    code = (store or {}).get("store_code") or store_code
    result = {"platform": None, "legacy": None, "errors": []}
    if store:
        try:
            result["platform"] = repo.set_platform_flag(
                store["tenant_id"], store["store_id"], product_code, bill_no, bill_date, dont_consider)
        except Exception as exc:
            logger.exception("DontConsiderInOrder platform write failed")
            result["errors"].append(f"Platform: {exc}")
    if code:
        invalidate_legacy_cache(code)
        try:
            result["legacy"] = repo.set_legacy_flag(code, product_code, bill_no, bill_date, dont_consider)
        except legacy_database.LegacyDatabaseUnavailable as exc:
            result["errors"].append(f"Order database: {exc}")
        except Exception as exc:
            logger.exception("DontConsiderInOrder legacy write failed")
            result["errors"].append(f"Order database: {exc}")
    if not (result["platform"] or result["legacy"]):
        detail = "; ".join(result["errors"]) or "No sale lines matched this bill."
        raise HTTPException(status_code=409 if not result["errors"] else 503, detail=detail)
    result["dont_consider"] = bool(dont_consider)
    logger.info("DontConsiderInOrder store=%s product=%s bill=%s date=%s -> %s (platform=%s legacy=%s)",
                code, product_code, bill_no, bill_date, dont_consider, result["platform"], result["legacy"])
    return result
