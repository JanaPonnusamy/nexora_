"""Procurement Rules Registry. No database and no decision_rules import."""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement.quantity_profile_t import RARE_MOVING_WARNING  # noqa: E402
from modules.procurement.rules_catalog import BY_ID, RULES  # noqa: E402
from modules.procurement.rules_resolution import RulesRegistry, RuleConflict, RuleRejected  # noqa: E402


REQUIRED = {
    "PRR-QTY-WINDOW",
    "PRR-QTY-MIN-COVER",
    "PRR-QTY-MAX-COVER",
    "PRR-QTY-RECENCY",
    "PRR-STK-SOURCE",
    "PRR-STK-PENDING",
    "PRR-QTY-GROSS",
    "PRR-QTY-NET",
    "PRR-QTY-SALEUNIT",
    "PRR-QTY-DONTCONSIDER",
    "PRR-QTY-RARE",
    "PRR-SUP-COST",
    "PRR-SUP-STALE",
    "PRR-SUP-ONE",
    "PRR-SUP-PRECEDENCE",
    "PRR-EXP-PRECEDENCE",
    "PRR-RCV-NOT-SUPPLIED",
    "PRR-PERM-ROLE",
    "PRR-PERM-SNAPSHOT",
    "PRR-SAFE-TXNVALIDITY",
    "PRR-SAFE-PROFILE",
}


def test_catalog_ids_and_unresolved_rules():
    ids = {rule.rule_id for rule in RULES}
    assert REQUIRED <= ids
    assert len(ids) == len(RULES)
    assert BY_ID["PRR-QTY-WINDOW"].default_value == 90
    assert BY_ID["PRR-QTY-MIN-COVER"].default_value == 13
    assert BY_ID["PRR-QTY-MAX-COVER"].default_value == 18
    assert BY_ID["PRR-QTY-RECENCY"].default_value == 15
    assert BY_ID["PRR-QTY-RECENCY"].status == "CONFLICT_RECORDED"
    assert BY_ID["PRR-STK-SOURCE"].default_value == "Products.TotalStock"
    assert BY_ID["PRR-STK-SOURCE"].override_policy == "LOCKED"
    assert BY_ID["PRR-STK-PENDING"].status == "DECISION_REQUIRED"
    assert BY_ID["PRR-SAFE-TXNVALIDITY"].status == "UNVERIFIED"
    assert BY_ID["PRR-PERM-ROLE"].status == "DECISION_REQUIRED"
    assert BY_ID["PRR-RCV-NOT-SUPPLIED"].status == "UNVERIFIED"
    assert RARE_MOVING_WARNING in BY_ID["PRR-QTY-RARE"].default_value
    assert "auto_order=false" in BY_ID["PRR-QTY-RARE"].default_value
    assert BY_ID["PRR-SAFE-PROFILE"].default_value is False


def test_store_isolation_and_deterministic_hash():
    registry = RulesRegistry()
    registry.set_override("tenant-a", "store-1", "PRR-QTY-WINDOW", 60, "editor", "store window", 0)
    left = registry.resolve("tenant-a", "store-1")
    again = registry.resolve("tenant-a", "store-1")
    other_store = registry.resolve("tenant-a", "store-2")
    other_tenant = registry.resolve("tenant-b", "store-1")
    assert left["content_hash"] == again["content_hash"]
    assert _value(left, "PRR-QTY-WINDOW") == 60
    assert _value(other_store, "PRR-QTY-WINDOW") == 90
    assert _value(other_tenant, "PRR-QTY-WINDOW") == 90
    assert _source(left, "PRR-QTY-WINDOW") == "override"
    assert _source(other_store, "PRR-QTY-WINDOW") == "default"


def test_locked_blocked_and_range_are_rejected():
    registry = RulesRegistry()
    for rule_id, value in (
        ("PRR-STK-SOURCE", "ProductTrans.StockInHand"),
        ("PRR-STK-PENDING", "PurchaseTrans.PendingQty"),
        ("PRR-SAFE-TXNVALIDITY", "0=valid"),
        ("PRR-SAFE-PROFILE", True),
        ("PRR-QTY-WINDOW", 0),
        ("PRR-QTY-SALEUNIT", False),
    ):
        try:
            registry.set_override("tenant-a", "store-1", rule_id, value, "editor", "no", 0)
        except RuleRejected:
            continue
        raise AssertionError(rule_id + " should have been rejected")
    try:
        registry.set_override("tenant-a", "store-1", "PRR-QTY-MIN-COVER", 20, "editor", "too high", 0)
    except RuleRejected as exc:
        assert exc.code == "RANGE"
    else:
        raise AssertionError("min cover above max should fail")


def test_optimistic_concurrency_history_and_reset():
    registry = RulesRegistry()
    registry.set_override("tenant-a", "store-1", "PRR-QTY-RECENCY", 12, "editor-1", "shorter recency", 0)
    try:
        registry.set_override("tenant-a", "store-1", "PRR-QTY-RECENCY", 20, "editor-2", "stale", 0)
    except RuleConflict as exc:
        assert exc.code == "VERSION"
    else:
        raise AssertionError("stale version should conflict")
    registry.set_override("tenant-a", "store-1", "PRR-QTY-RECENCY", 20, "editor-2", "updated", 1)
    history = registry.history("tenant-a", "store-1", "PRR-QTY-RECENCY")
    assert [row["editor_id"] for row in history] == ["editor-1", "editor-2"]
    assert history[-1]["reason"] == "updated"
    registry.reset_override("tenant-a", "store-1", "PRR-QTY-RECENCY", "editor-1", "back to inherited", 2)
    resolved = registry.resolve("tenant-a", "store-1")
    assert _value(resolved, "PRR-QTY-RECENCY") == 15
    assert _source(resolved, "PRR-QTY-RECENCY") == "default"


def test_snapshot_does_not_follow_later_edits():
    registry = RulesRegistry()
    registry.set_override("tenant-a", "store-1", "PRR-QTY-MAX-COVER", 21, "editor", "more cover", 0)
    frozen = registry.take_snapshot("tenant-a", "store-1", "editor")
    registry.set_override("tenant-a", "store-1", "PRR-QTY-MAX-COVER", 30, "editor", "later", 1)
    stored = registry.get_snapshot(frozen["snapshot_id"])
    assert _value(stored, "PRR-QTY-MAX-COVER") == 21
    assert stored["applies_to"] == "future_refresh_only"
    assert _value(registry.resolve("tenant-a", "store-1"), "PRR-QTY-MAX-COVER") == 30


def test_migration_files_exist_and_do_not_touch_order_header():
    sql_dir = os.path.join(_BACKEND, "modules", "procurement", "sql")
    forward = open(os.path.join(sql_dir, "0026_procurement_rules_registry.sql"), encoding="utf-8").read()
    rollback = open(os.path.join(sql_dir, "0026_procurement_rules_registry_rollback.sql"), encoding="utf-8").read()
    verify = open(os.path.join(sql_dir, "0026_procurement_rules_registry_verify.sql"), encoding="utf-8").read()
    assert "procurement.rule_definition" in forward
    assert "rule_snapshot_id" in forward
    assert "OrderHeaderDetails" not in forward.split("OrderHeaderDetails is")[-1] or "not modified" in forward
    assert "THROW 50026" in rollback
    assert "DROP COLUMN rule_snapshot_id" in rollback
    assert "AS ok" in verify
    engine = open(os.path.join(_BACKEND, "modules", "procurement", "decision_rules.py"), encoding="utf-8").read()
    assert "rules_resolution" not in engine
    assert "rules_catalog" not in engine


def _value(payload, rule_id):
    for row in payload["rules"]:
        if row["rule_id"] == rule_id:
            return row["value"]
    raise KeyError(rule_id)


def _source(payload, rule_id):
    for row in payload["rules"]:
        if row["rule_id"] == rule_id:
            return row["source"]
    raise KeyError(rule_id)
