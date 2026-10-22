"""Effective-rule resolution for the Procurement Rules Registry.

Loads catalog defaults and store overrides, validates them, and can freeze
a snapshot. It does not call decision_rules.evaluate and it does not
recalculate an existing refresh.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from modules.procurement.rules_catalog import (
    POLICY_NONE,
    POLICY_STORE,
    RULES,
    RuleDef,
    require_rule,
)

MIN_COVER_ID = "PRR-QTY-MIN-COVER"
MAX_COVER_ID = "PRR-QTY-MAX-COVER"


class RuleRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class RuleConflict(RuleRejected):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def validate_value(rule: RuleDef, value) -> object:
    if rule.value_type == "blocked" or rule.override_policy == POLICY_NONE:
        raise RuleRejected("BLOCKED", rule.rule_id + " has no accepted value.")
    if rule.value_type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuleRejected("TYPE", rule.rule_id + " requires an integer.")
        if rule.min_value is not None and value < rule.min_value:
            raise RuleRejected("RANGE", rule.rule_id + " is below " + str(rule.min_value) + ".")
        if rule.max_value is not None and value > rule.max_value:
            raise RuleRejected("RANGE", rule.rule_id + " is above " + str(rule.max_value) + ".")
        return value
    if rule.value_type == "bool":
        if not isinstance(value, bool):
            raise RuleRejected("TYPE", rule.rule_id + " requires true or false.")
        if rule.rule_id in {"PRR-QTY-SALEUNIT", "PRR-QTY-DONTCONSIDER", "PRR-SUP-ONE"} and value is not True:
            raise RuleRejected("LOCKED_VALUE", rule.rule_id + " cannot be turned off.")
        if rule.rule_id == "PRR-SAFE-PROFILE" and value is not False:
            raise RuleRejected("ROLLOUT", "Profile T cannot be enabled from the registry.")
        return value
    if rule.value_type == "enum":
        if rule.allowed_values is not None and value not in rule.allowed_values:
            raise RuleRejected("ENUM", rule.rule_id + " rejects that value.")
        return value
    if rule.value_type == "text":
        if not isinstance(value, str) or not value.strip():
            raise RuleRejected("TYPE", rule.rule_id + " requires text.")
        if rule.override_policy == POLICY_LOCKED and value != rule.default_value:
            raise RuleRejected("LOCKED_VALUE", rule.rule_id + " text is locked.")
        return value
    raise RuleRejected("TYPE", rule.rule_id + " has an unsupported type.")


class RulesRegistry:
    """Process store. SQL migration 0026 is the durable shape and is not applied here."""

    def __init__(self):
        self._lock = threading.Lock()
        self._defaults = {rule.rule_id: {"value": rule.default_value, "row_version": 1} for rule in RULES}
        self._overrides: dict[tuple, dict] = {}
        self._audit: list[dict] = []
        self._snapshots: dict[str, dict] = {}

    def catalog(self) -> list[dict]:
        return [rule.public() for rule in RULES]

    def _effective_unlocked(self, tenant_id: str, store_id: str) -> list[dict]:
        rows = []
        for rule in RULES:
            default = self._defaults[rule.rule_id]
            key = (tenant_id, store_id, rule.rule_id)
            override = self._overrides.get(key)
            if override is None:
                rows.append({
                    "rule_id": rule.rule_id,
                    "value": default["value"],
                    "source": "default",
                    "row_version": default["row_version"],
                    "default_row_version": default["row_version"],
                    "status": rule.status,
                    "override_policy": rule.override_policy,
                    "inherited_value": default["value"],
                })
            else:
                rows.append({
                    "rule_id": rule.rule_id,
                    "value": override["value"],
                    "source": "override",
                    "row_version": override["row_version"],
                    "default_row_version": default["row_version"],
                    "status": rule.status,
                    "override_policy": rule.override_policy,
                    "inherited_value": default["value"],
                })
        return rows

    def resolve(self, tenant_id: str, store_id: str) -> dict:
        with self._lock:
            rows = self._effective_unlocked(tenant_id, store_id)
        payload = [
            {"rule_id": row["rule_id"], "value": row["value"], "source": row["source"]}
            for row in rows
        ]
        digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        return {
            "tenant_id": tenant_id,
            "store_id": store_id,
            "content_hash": digest,
            "live_engine_unchanged": True,
            "affects_future_calculations_only": True,
            "rules": rows,
        }

    def _cover_ok(self, values: dict):
        minimum = values.get(MIN_COVER_ID)
        maximum = values.get(MAX_COVER_ID)
        if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
            raise RuleRejected("RANGE", "Minimum cover cannot exceed maximum cover.")

    def _check_cover(self, tenant_id: str, store_id: str, rule_id: str, value):
        rows = {row["rule_id"]: row["value"] for row in self._effective_unlocked(tenant_id, store_id)}
        rows[rule_id] = value
        self._cover_ok(rows)

    def _check_default_cover(self, rule_id: str, value):
        defaults = {rid: row["value"] for rid, row in self._defaults.items()}
        defaults[rule_id] = value
        self._cover_ok(defaults)
        stores = {(tenant, store) for tenant, store, _rule in self._overrides}
        for tenant_id, store_id in stores:
            rows = {row["rule_id"]: row["value"] for row in self._effective_unlocked(tenant_id, store_id)}
            if (tenant_id, store_id, rule_id) not in self._overrides:
                rows[rule_id] = value
            self._cover_ok(rows)

    def set_default(self, rule_id: str, value, editor_id: str, reason: str, expected_version: int):
        rule = require_rule(rule_id)
        if rule.override_policy != POLICY_STORE:
            raise RuleRejected("LOCKED", rule_id + " default cannot be edited.")
        if not reason or not str(reason).strip():
            raise RuleRejected("REASON", "A reason is required.")
        cleaned = validate_value(rule, value)
        with self._lock:
            current = self._defaults[rule_id]
            if current["row_version"] != expected_version:
                raise RuleConflict("VERSION", rule_id + " default was edited by someone else.")
            self._check_default_cover(rule_id, cleaned)
            previous = current["value"]
            current["value"] = cleaned
            current["row_version"] += 1
            self._audit.append({
                "audit_id": str(uuid.uuid4()),
                "tenant_id": None,
                "store_id": None,
                "rule_id": rule_id,
                "change_kind": "DEFAULT",
                "previous_value": previous,
                "new_value": cleaned,
                "editor_id": editor_id,
                "reason": reason.strip(),
                "changed_at": _now(),
                "row_version": current["row_version"],
            })
            return deepcopy(current)

    def set_override(
        self,
        tenant_id: str,
        store_id: str,
        rule_id: str,
        value,
        editor_id: str,
        reason: str,
        expected_version: int | None,
    ):
        rule = require_rule(rule_id)
        if rule.override_policy != POLICY_STORE:
            raise RuleRejected("LOCKED", rule_id + " cannot be overridden for a store.")
        if not reason or not str(reason).strip():
            raise RuleRejected("REASON", "A reason is required.")
        cleaned = validate_value(rule, value)
        key = (tenant_id, store_id, rule_id)
        with self._lock:
            current = self._overrides.get(key)
            current_version = 0 if current is None else current["row_version"]
            if expected_version is not None and expected_version != current_version:
                raise RuleConflict("VERSION", rule_id + " override was edited by someone else.")
            self._check_cover(tenant_id, store_id, rule_id, cleaned)
            previous = None if current is None else current["value"]
            row_version = current_version + 1
            self._overrides[key] = {
                "value": cleaned,
                "row_version": row_version,
                "editor_id": editor_id,
                "reason": reason.strip(),
                "updated_at": _now(),
            }
            self._audit.append({
                "audit_id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "store_id": store_id,
                "rule_id": rule_id,
                "change_kind": "OVERRIDE",
                "previous_value": previous,
                "new_value": cleaned,
                "editor_id": editor_id,
                "reason": reason.strip(),
                "changed_at": _now(),
                "row_version": row_version,
            })
            return deepcopy(self._overrides[key])

    def reset_override(self, tenant_id: str, store_id: str, rule_id: str, editor_id: str, reason: str, expected_version: int):
        require_rule(rule_id)
        if not reason or not str(reason).strip():
            raise RuleRejected("REASON", "A reason is required.")
        key = (tenant_id, store_id, rule_id)
        with self._lock:
            current = self._overrides.get(key)
            if current is None:
                raise RuleRejected("ABSENT", rule_id + " has no store override.")
            if current["row_version"] != expected_version:
                raise RuleConflict("VERSION", rule_id + " override was edited by someone else.")
            previous = current["value"]
            del self._overrides[key]
            self._audit.append({
                "audit_id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "store_id": store_id,
                "rule_id": rule_id,
                "change_kind": "RESET",
                "previous_value": previous,
                "new_value": self._defaults[rule_id]["value"],
                "editor_id": editor_id,
                "reason": reason.strip(),
                "changed_at": _now(),
                "row_version": current["row_version"] + 1,
            })

    def history(self, tenant_id: str | None = None, store_id: str | None = None, rule_id: str | None = None) -> list[dict]:
        with self._lock:
            rows = list(self._audit)
        if tenant_id is not None:
            rows = [row for row in rows if row["tenant_id"] == tenant_id]
        if store_id is not None:
            rows = [row for row in rows if row["store_id"] == store_id]
        if rule_id is not None:
            rows = [row for row in rows if row["rule_id"] == rule_id]
        return rows

    def take_snapshot(self, tenant_id: str, store_id: str, editor_id: str) -> dict:
        """Freeze the current effective set for a future refresh. Does not write a refresh row."""
        resolved = self.resolve(tenant_id, store_id)
        snapshot_id = str(uuid.uuid4())
        body = {
            "snapshot_id": snapshot_id,
            "tenant_id": tenant_id,
            "store_id": store_id,
            "content_hash": resolved["content_hash"],
            "created_at": _now(),
            "created_by": editor_id,
            "applies_to": "future_refresh_only",
            "rules": deepcopy(resolved["rules"]),
        }
        with self._lock:
            self._snapshots[snapshot_id] = body
        return deepcopy(body)

    def get_snapshot(self, snapshot_id: str) -> dict:
        with self._lock:
            body = self._snapshots.get(snapshot_id)
        if body is None:
            raise RuleRejected("ABSENT", "Snapshot was not found.")
        return deepcopy(body)


REGISTRY = RulesRegistry()
