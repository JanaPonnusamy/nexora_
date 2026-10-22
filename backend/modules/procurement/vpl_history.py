"""VPL working-line refresh and history.

This is not wired into decision_rules.evaluate, decision_service, or
decision_repository.clear_products. The live generator still deletes
virtual-product rows for one refresh_id without copying them. Callers
must opt into VplWorkspace.

Confirmed supplier pending, transactionvalidity, and Role 1/2 are not
interpreted. rule_snapshot_id is stored as given and is not recomputed.

Finding 2 (conversation approval, Option A): a manually touched line
whose product is absent from the next generated list stays visible in
`removed_manual_review`. It is not an active orderable line. Removal
fields exist only on this in-memory model. Migration 0027 is not applied
and does not contain those fields.

Line identity (corrected 2026-10-20, temporary-implementer pass): the
real `procurement_order_items` table is unique on `(refresh_id,
product_id)`, not `product_code` (`0004_...sql`). `product_code` is
nullable there. A line's identity key here is `product_id` when the
caller supplies one; only when `product_id` is absent does the key fall
back to `product_code`. Two lines are never merged because they share a
`product_code` if either has a distinct or missing `product_id`. A line
with neither a `product_id` nor a `product_code` is rejected (`IDENTITY`)
-- there is nothing stable to key it on. `PHASE_2_VPL_HISTORY.md`'s
"Lifecycle" step 2 and "Canonical field mapping" row previously said the
key was `product_code` alone; that statement is superseded by this one.

Skip-versus-removal precedence (corrected 2026-10-20): a skip alone is
operational, not evidence of a manual edit, and must not route a line
into `removed_manual_review` when it drops out of a later generation --
it is just gone from the live set, recoverable only from history, same
as any other untouched absent line. `_touched()` below no longer treats
`reviewed_at` by itself as sufficient; it requires manual_override,
supplier_code, or rare_confirmed, or an explicit `skipped` status (which
is routed to `carry_forward_skips`-style retention, not manual review).
See `_touched()` and `_is_skip_only()`.
"""

from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone


REMOVED_SECTION = "Removed from Current Suggestions — Manual Review"
_REMOVAL_FIELDS = (
    "section",
    "originating_refresh_id",
    "originating_cycle_id",
    "removed_during_refresh_id",
    "removed_at",
    "removed_by",
)


class VplError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class VplConflict(VplError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _key(product_id, product_code):
    """Stable line-identity key: product_id when present, else
    product_code. Tagged with which kind it is so a product_id key and a
    product_code key never collide by accident (e.g. a numeric
    product_id that happens to equal some other line's product_code
    string)."""
    if product_id is not None:
        return ("id", product_id)
    if product_code:
        return ("code", product_code)
    return None


def _is_skip_only(line: dict) -> bool:
    """A line whose only 'touched' signal is a skip (item_status ==
    'skipped') and reviewed_at being set by that skip, with no manual
    quantity override, no supplier assignment, and no rare-mover
    confirmation. skip_item() in workspace_repository.py sets
    reviewed_at = GETDATE() without setting manual_override -- that
    alone must not make this line look manually edited."""
    return bool(
        line.get("item_status") == "skipped"
        and not line.get("manual_override")
        and not line.get("supplier_code")
        and not line.get("rare_confirmed")
    )


def _sort_token(key) -> tuple:
    """Deterministic, always-comparable ordering token for one identity
    key, independent of product_code. ("id", ...) sorts before
    ("code", ...) so a mixed working set has a stable, total order even
    when two keys are of different kinds; within one kind the raw value
    is compared directly (product_id is always an int/str when present;
    product_code is always a str when it is the key, per _key())."""
    kind, value = key
    return (0 if kind == "id" else 1, value)


def _sorted_by_identity(keyed: dict) -> list:
    """Sort a {identity_key: line} mapping into a list, ordered first by
    product_code (None-safe: null codes sort after any string code) and
    then by the stable identity key as a tiebreaker. This fixes the
    crash where line["product_code"] was compared directly and Python
    cannot order None against str, or None against None. Two lines that
    share one product_code (distinct product_id) still get a
    deterministic relative order via the identity-key tiebreaker rather
    than an arbitrary dict-iteration order."""
    pairs = list(keyed.items())
    pairs.sort(
        key=lambda pair: (
            pair[1]["product_code"] is None,
            pair[1]["product_code"] or "",
            _sort_token(pair[0]),
        )
    )
    return [line for _, line in pairs]


def _touched(line: dict) -> bool:
    """A line is carry-forward-worthy ('touched') only when it carries a
    genuine manual quantity edit, a live supplier assignment, or a
    rare-mover confirmation. A skip by itself (item_status == 'skipped',
    which also sets reviewed_at) is explicitly excluded -- see
    _is_skip_only(). reviewed_at alone (e.g. restore_item/defer_item
    touching it without an override) is likewise not sufficient; only
    manual_override, supplier_code, and rare_confirmed are evidence of an
    edit worth preserving in removed_manual_review."""
    if _is_skip_only(line):
        return False
    return bool(
        line.get("manual_override")
        or line.get("supplier_code")
        or line.get("rare_confirmed")
    )


class VplWorkspace:
    def __init__(self):
        self._lock = threading.Lock()
        self._working: dict[tuple, dict] = {}
        self._history: list[dict] = []

    def open_cycle(self, tenant_id: str, store_id: str, cycle_id: str, lines: list[dict], rule_snapshot_id: str | None):
        key = (tenant_id, store_id, cycle_id)
        with self._lock:
            if key in self._working:
                raise VplConflict("DUPLICATE_CYCLE", "This store cycle already has a working VPL.")
            refresh_id = str(uuid.uuid4())
            stored = self._index(lines, refresh_id, carried=False)
            self._working[key] = {
                "tenant_id": tenant_id,
                "store_id": store_id,
                "cycle_id": cycle_id,
                "refresh_id": refresh_id,
                "rule_snapshot_id": rule_snapshot_id,
                "lines": stored,
                "removed_manual_review": {},
            }
            return self._public(self._working[key])

    def working(self, tenant_id: str, store_id: str, cycle_id: str) -> dict:
        with self._lock:
            return self._public(self._require(tenant_id, store_id, cycle_id))

    def edit(self, tenant_id: str, store_id: str, cycle_id: str, product_code: str, changes: dict, expected_version: int, editor_id: str):
        with self._lock:
            body = self._require(tenant_id, store_id, cycle_id)
            key = self._resolve_by_code(body["lines"], product_code)
            line = body["lines"].get(key) if key is not None else None
            if line is None:
                if self._resolve_by_code(body["removed_manual_review"], product_code) is not None:
                    raise VplError(
                        "NOT_ORDERABLE",
                        REMOVED_SECTION + ". A removed manual-review line cannot be edited into an order.",
                    )
                raise VplError("ABSENT", "Working line was not found.")
            if line["row_version"] != expected_version:
                raise VplConflict("VERSION", "The working line was edited by someone else.")
            allowed = {"final_qty", "manual_override", "supplier_code", "assigned_qty", "rare_confirmed", "reviewed_at", "reason_code"}
            unknown = set(changes) - allowed
            if unknown:
                raise VplError("FIELD", "Unknown edit fields: " + ", ".join(sorted(unknown)))
            line.update(changes)
            line["manual_override"] = True
            line["updated_by"] = editor_id
            line["updated_at"] = _now()
            line["row_version"] += 1
            return deepcopy(line)

    def assign_supplier(self, tenant_id: str, store_id: str, cycle_id: str, product_code: str):
        return self._guard_orderable(tenant_id, store_id, cycle_id, product_code, "Assignment")

    def export_lines(self, tenant_id: str, store_id: str, cycle_id: str, product_code: str):
        return self._guard_orderable(tenant_id, store_id, cycle_id, product_code, "Export")

    def place_order(self, tenant_id: str, store_id: str, cycle_id: str, product_code: str):
        return self._guard_orderable(tenant_id, store_id, cycle_id, product_code, "Ordering")

    def submit_to_portal(self, tenant_id: str, store_id: str, cycle_id: str, product_code: str):
        return self._guard_orderable(tenant_id, store_id, cycle_id, product_code, "Portal submission")

    def refresh(
        self,
        tenant_id: str,
        store_id: str,
        cycle_id: str,
        generated: list[dict],
        rule_snapshot_id: str | None,
        editor_id: str,
        before_commit=None,
    ):
        """Copy the current active set into history, then open a new refresh.

        User-touched lines that are still generated keep final quantity,
        supplier, review, and rare-mover confirmation. Untouched survivors
        take the new suggestion. Both increment row_version.

        A touched line absent from the new list moves into
        removed_manual_review. It is not orderable. Repeating the refresh
        while it stays absent leaves that one record in place. If the
        product is generated again, it returns to the active set under the
        same touched-line contract and leaves the review collection. The
        removal episode remains only in the history batch written when it
        left the active set.

        If staging or before_commit fails, the working set and the history
        list stay as they were.
        """
        with self._lock:
            current = self._require(tenant_id, store_id, cycle_id)
            backup = deepcopy(current)
            new_refresh_id = str(uuid.uuid4())
            incoming = self._index(generated, new_refresh_id, carried=False)
            new_lines = {}
            new_removed = deepcopy(backup["removed_manual_review"])
            for item_key, suggestion in incoming.items():
                previous = backup["lines"].get(item_key)
                held = new_removed.pop(item_key, None)
                source = previous if previous is not None else held
                if source is not None and _touched(source):
                    new_lines[item_key] = self._restore_touched(source, suggestion, new_refresh_id, editor_id)
                else:
                    if source is not None:
                        suggestion["row_version"] = source["row_version"] + 1
                    new_lines[item_key] = suggestion
            for item_key, previous in backup["lines"].items():
                if item_key in incoming:
                    continue
                if _is_skip_only(previous):
                    continue
                if not _touched(previous):
                    continue
                if item_key in new_removed:
                    raise VplConflict(
                        "DUPLICATE_LINE",
                        "Duplicate line identity " + repr(item_key) + ".",
                    )
                new_removed[item_key] = self._as_removed(previous, backup, new_refresh_id, editor_id)
            staged = {
                "history_id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "store_id": store_id,
                "cycle_id": cycle_id,
                "source_refresh_id": backup["refresh_id"],
                "rule_snapshot_id": backup["rule_snapshot_id"],
                "created_at": _now(),
                "created_by": editor_id,
                "line_count": len(backup["lines"]),
                "lines": list(backup["lines"].values()),
            }
            if before_commit is not None:
                before_commit()
            self._history.append(staged)
            current["refresh_id"] = new_refresh_id
            current["rule_snapshot_id"] = rule_snapshot_id
            current["lines"] = new_lines
            current["removed_manual_review"] = new_removed
            return {
                "working": self._public(current),
                "history_id": staged["history_id"],
            }

    def history_headers(self, tenant_id: str, store_id: str, limit: int | None = 10) -> dict:
        with self._lock:
            rows = [
                {key: value for key, value in row.items() if key != "lines"}
                for row in self._history
                if row["tenant_id"] == tenant_id and row["store_id"] == store_id
            ]
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        total = len(rows)
        if limit is not None:
            rows = rows[:limit]
        return {"total": total, "returned": len(rows), "headers": rows}

    def history_detail(self, history_id: str) -> dict:
        with self._lock:
            for row in self._history:
                if row["history_id"] == history_id:
                    return deepcopy(row)
        raise VplError("ABSENT", "History batch was not found.")

    def _guard_orderable(self, tenant_id, store_id, cycle_id, product_code, action):
        with self._lock:
            body = self._require(tenant_id, store_id, cycle_id)
            if self._resolve_by_code(body["removed_manual_review"], product_code) is not None:
                raise VplError(
                    "NOT_ORDERABLE",
                    REMOVED_SECTION + ". " + action + " is prohibited for a removed manual-review line.",
                )
            key = self._resolve_by_code(body["lines"], product_code)
            line = body["lines"].get(key) if key is not None else None
            if line is None:
                raise VplError("ABSENT", "Working line was not found.")
            if line.get("orderable") is False:
                raise VplError("NOT_ORDERABLE", action + " is prohibited.")
            return {
                "accepted": True,
                "action": action,
                "product_code": product_code,
                "orderable": True,
                "live_generation_unchanged": True,
            }

    def _restore_touched(self, source: dict, suggestion: dict, refresh_id: str, editor_id: str) -> dict:
        kept = deepcopy(source)
        for field in _REMOVAL_FIELDS:
            kept.pop(field, None)
        kept["orderable"] = True
        kept["refresh_id"] = refresh_id
        kept["suggested_qty"] = suggestion["suggested_qty"]
        kept["carried_forward"] = True
        kept["row_version"] = source["row_version"] + 1
        kept["updated_by"] = editor_id
        kept["updated_at"] = _now()
        return kept

    def _as_removed(self, previous: dict, backup: dict, new_refresh_id: str, editor_id: str) -> dict:
        moved = deepcopy(previous)
        moved["orderable"] = False
        moved["section"] = REMOVED_SECTION
        moved["originating_refresh_id"] = previous.get("refresh_id")
        moved["originating_cycle_id"] = backup["cycle_id"]
        moved["removed_during_refresh_id"] = new_refresh_id
        moved["removed_at"] = _now()
        moved["removed_by"] = editor_id
        moved["row_version"] = previous["row_version"] + 1
        return moved

    def _resolve_by_code(self, keyed: dict, product_code):
        """Public router methods take product_code. Resolve it to the
        internal (kind, value) key. Returns None if no line in `keyed`
        has that product_code. Raises AMBIGUOUS if more than one line
        shares that code with a distinct product_id -- the caller asked
        by code alone and that is no longer guaranteed unique."""
        matches = [k for k, line in keyed.items() if line.get("product_code") == product_code]
        if not matches:
            return None
        if len(matches) > 1:
            raise VplError(
                "AMBIGUOUS",
                "Multiple lines share product_code " + str(product_code) + "; identify by product_id.",
            )
        return matches[0]

    def _require(self, tenant_id, store_id, cycle_id):
        body = self._working.get((tenant_id, store_id, cycle_id))
        if body is None:
            raise VplError("ABSENT", "No working VPL for this store cycle.")
        body.setdefault("removed_manual_review", {})
        return body

    def _index(self, lines: list[dict], refresh_id: str, carried: bool) -> dict:
        indexed = {}
        for raw in lines:
            code = raw.get("product_code")
            product_id = raw.get("product_id")
            key = _key(product_id, code)
            if key is None:
                raise VplError("IDENTITY", "A working line needs a product_id or a product_code.")
            if key in indexed:
                raise VplConflict(
                    "DUPLICATE_LINE",
                    "Duplicate line identity " + repr(key) + ".",
                )
            indexed[key] = {
                "refresh_id": refresh_id,
                "product_code": code,
                "product_id": raw.get("product_id"),
                "item_status": raw.get("item_status"),
                "suggested_qty": raw.get("suggested_qty"),
                "final_qty": raw.get("final_qty", raw.get("suggested_qty")),
                "manual_override": bool(raw.get("manual_override")),
                "supplier_code": raw.get("supplier_code"),
                "assigned_qty": raw.get("assigned_qty"),
                "rare_confirmed": bool(raw.get("rare_confirmed")),
                "reviewed_at": raw.get("reviewed_at"),
                "reason_code": raw.get("reason_code"),
                "row_version": int(raw.get("row_version") or 1),
                "carried_forward": carried,
                "orderable": True,
                "updated_by": raw.get("updated_by"),
                "updated_at": raw.get("updated_at"),
            }
        return indexed

    def _public(self, body: dict) -> dict:
        lines = _sorted_by_identity(body["lines"])
        removed = _sorted_by_identity(body.get("removed_manual_review", {}))
        return {
            "tenant_id": body["tenant_id"],
            "store_id": body["store_id"],
            "cycle_id": body["cycle_id"],
            "refresh_id": body["refresh_id"],
            "rule_snapshot_id": body["rule_snapshot_id"],
            "lines": deepcopy(lines),
            "removed_manual_review": {
                "section": REMOVED_SECTION,
                "orderable": False,
                "lines": deepcopy(removed),
            },
        }


WORKSPACE = VplWorkspace()
