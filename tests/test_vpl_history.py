"""Phase 2 VPL history. No database and no decision engine."""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement.vpl_history import VplConflict, VplError, VplWorkspace  # noqa: E402


def _line(code, suggested, **extra):
    body = {"product_code": code, "suggested_qty": suggested, "final_qty": suggested}
    body.update(extra)
    return body


def test_refresh_keeps_history_and_manual_edits():
    workspace = VplWorkspace()
    opened = workspace.open_cycle("t1", "s1", "c1", [_line("A", 5), _line("B", 2)], "snap-1")
    workspace.edit("t1", "s1", "c1", "A", {"final_qty": 9, "supplier_code": "SUP"}, 1, "pm")
    result = workspace.refresh(
        "t1", "s1", "c1",
        [_line("A", 4), _line("B", 7), _line("C", 1)],
        "snap-2",
        "pm",
    )
    by_code = {line["product_code"]: line for line in result["working"]["lines"]}
    assert by_code["A"]["final_qty"] == 9
    assert by_code["A"]["suggested_qty"] == 4
    assert by_code["A"]["supplier_code"] == "SUP"
    assert by_code["A"]["carried_forward"] is True
    assert by_code["B"]["final_qty"] == 7
    assert by_code["C"]["final_qty"] == 1
    detail = workspace.history_detail(result["history_id"])
    assert detail["rule_snapshot_id"] == "snap-1"
    assert detail["source_refresh_id"] == opened["refresh_id"]
    archived = {line["product_code"]: line for line in detail["lines"]}
    assert archived["A"]["final_qty"] == 9
    assert result["working"]["rule_snapshot_id"] == "snap-2"
    assert detail["rule_snapshot_id"] == "snap-1"


def test_failed_refresh_does_not_replace_working_or_history():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], "snap-1")
    before = workspace.working("t1", "s1", "c1")

    def fail():
        raise RuntimeError("generation failed")

    try:
        workspace.refresh("t1", "s1", "c1", [_line("A", 8)], "snap-2", "pm", before_commit=fail)
    except RuntimeError as exc:
        assert str(exc) == "generation failed"
    else:
        raise AssertionError("refresh should have failed")
    after = workspace.working("t1", "s1", "c1")
    assert after["refresh_id"] == before["refresh_id"]
    assert after["lines"][0]["final_qty"] == 5
    assert workspace.history_headers("t1", "s1", limit=None)["total"] == 0


def test_duplicate_line_and_stale_edit_are_rejected():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], None)
    try:
        workspace.refresh("t1", "s1", "c1", [_line("A", 1), _line("A", 2)], None, "pm")
    except VplConflict as exc:
        assert exc.code == "DUPLICATE_LINE"
    else:
        raise AssertionError("duplicate product should conflict")
    assert workspace.history_headers("t1", "s1", limit=None)["total"] == 0
    try:
        workspace.edit("t1", "s1", "c1", "A", {"final_qty": 3}, 0, "other")
    except VplConflict as exc:
        assert exc.code == "VERSION"
    else:
        raise AssertionError("stale version should conflict")
    edited = workspace.edit("t1", "s1", "c1", "A", {"final_qty": 3}, 1, "pm")
    assert edited["row_version"] == 2
    assert edited["final_qty"] == 3


def test_history_limit_does_not_drop_older_batches_and_stores_stay_separate():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 1)], "snap")
    workspace.open_cycle("t2", "s2", "c2", [_line("A", 1)], "snap")
    for index in range(11):
        workspace.refresh("t1", "s1", "c1", [_line("A", index + 2)], "snap", "pm")
    page = workspace.history_headers("t1", "s1", limit=10)
    assert page["returned"] == 10
    assert page["total"] == 11
    assert workspace.history_headers("t2", "s2", limit=10)["total"] == 0
    detail = workspace.history_detail(page["headers"][-1]["history_id"])
    assert detail["lines"]


def test_rare_mover_confirmation_survives_refresh():
    workspace = VplWorkspace()
    workspace.open_cycle(
        "t1", "s1", "c1",
        [_line("R", 1, reason_code="RARE_MOVING_MANUAL_REVIEW")],
        None,
    )
    workspace.edit("t1", "s1", "c1", "R", {"rare_confirmed": True, "reviewed_at": "2026-10-19T12:00:00"}, 1, "pm")
    result = workspace.refresh("t1", "s1", "c1", [_line("R", 0, reason_code="ZERO_NET")], None, "pm")
    line = result["working"]["lines"][0]
    assert line["rare_confirmed"] is True
    assert line["final_qty"] == 1
    assert line["suggested_qty"] == 0
    assert line["carried_forward"] is True


def test_migration_sql_is_additive_and_engine_is_untouched():
    sql_dir = os.path.join(_BACKEND, "modules", "procurement", "sql")
    forward = open(os.path.join(sql_dir, "0027_vpl_history.sql"), encoding="utf-8").read()
    rollback = open(os.path.join(sql_dir, "0027_vpl_history_rollback.sql"), encoding="utf-8").read()
    verify = open(os.path.join(sql_dir, "0027_vpl_history_verify.sql"), encoding="utf-8").read()
    assert "procurement.vpl_history_batch" in forward
    assert "procurement.vpl_history_line" in forward
    assert "row_version" in forward
    assert "OrderHeaderDetails" in forward and "does not alter it" in forward
    assert "DROP TABLE procurement.procurement_order_items" not in forward
    assert "THROW 50027" in rollback
    assert "AS ok" in verify
    engine = open(os.path.join(_BACKEND, "modules", "procurement", "decision_rules.py"), encoding="utf-8").read()
    repository = open(os.path.join(_BACKEND, "modules", "procurement", "decision_repository.py"), encoding="utf-8").read()
    assert "vpl_history" not in engine
    assert "vpl_history" not in repository


def test_untouched_line_version_advances_so_a_stale_edit_conflicts():
    """Confirmed defect from PHASE_2_CLAUDE_REVIEW / the edge suite: an
    untouched line used to keep row_version 1 after refresh, so a client
    holding the pre-refresh version could overwrite the new suggestion.
    Refresh now increments that version."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], "snap-1")
    before = workspace.working("t1", "s1", "c1")["lines"][0]["row_version"]
    workspace.refresh("t1", "s1", "c1", [_line("A", 9, supplier_code=None)], "snap-2", "pm")
    after = workspace.working("t1", "s1", "c1")["lines"][0]
    assert after["final_qty"] == 9
    assert after["suggested_qty"] == 9
    assert after["row_version"] == before + 1
    try:
        workspace.edit(
            "t1", "s1", "c1", "A",
            {"final_qty": 42, "supplier_code": "LATE", "rare_confirmed": True, "reviewed_at": "2026-10-19T12:00:00"},
            before, "late",
        )
    except VplConflict as exc:
        assert exc.code == "VERSION"
    else:
        raise AssertionError("stale pre-refresh version should conflict")
    unchanged = workspace.working("t1", "s1", "c1")["lines"][0]
    assert unchanged["final_qty"] == 9
    assert unchanged["suggested_qty"] == 9
    assert unchanged["supplier_code"] is None
    assert unchanged["rare_confirmed"] is False
    assert unchanged["reviewed_at"] is None
    assert unchanged["row_version"] == after["row_version"]


def test_repeated_refreshes_never_reuse_an_earlier_row_version():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 1), _line("B", 1, supplier_code="SUP")], "snap")
    seen = {workspace.working("t1", "s1", "c1")["lines"][0]["row_version"]}
    for step in range(4):
        workspace.refresh(
            "t1", "s1", "c1",
            [_line("A", step + 2), _line("B", step + 3, supplier_code="SUP")],
            "snap", "pm",
        )
        lines = {line["product_code"]: line for line in workspace.working("t1", "s1", "c1")["lines"]}
        assert lines["A"]["row_version"] not in seen
        assert lines["B"]["row_version"] not in seen
        assert lines["B"]["supplier_code"] == "SUP"
        assert lines["B"]["suggested_qty"] == step + 3
        seen.add(lines["A"]["row_version"])
        seen.add(lines["B"]["row_version"])


def test_touched_omission_moves_to_manual_review_and_preserves_values():
    """In-memory only. Option A: a touched line missing from the next
    generation is visible for review and is not an active orderable line."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5, product_id=11), _line("B", 2)], "snap-1")
    workspace.edit(
        "t1", "s1", "c1", "A",
        {"final_qty": 9, "supplier_code": "SUP", "rare_confirmed": True, "reviewed_at": "2026-10-19T12:00:00"},
        1, "pm",
    )
    result = workspace.refresh("t1", "s1", "c1", [_line("B", 3)], "snap-2", "pm")
    active = {line["product_code"]: line for line in result["working"]["lines"]}
    assert "A" not in active
    assert active["B"]["final_qty"] == 3
    assert active["B"]["orderable"] is True
    section = result["working"]["removed_manual_review"]
    assert section["section"] == "Removed from Current Suggestions — Manual Review"
    assert section["orderable"] is False
    removed = {line["product_code"]: line for line in section["lines"]}
    assert list(removed) == ["A"]
    kept = removed["A"]
    assert kept["final_qty"] == 9
    assert kept["supplier_code"] == "SUP"
    assert kept["reviewed_at"] == "2026-10-19T12:00:00"
    assert kept["rare_confirmed"] is True
    assert kept["product_id"] == 11
    assert kept["orderable"] is False
    assert kept["originating_cycle_id"] == "c1"
    assert kept["row_version"] == 3
    detail = workspace.history_detail(result["history_id"])
    assert detail["rule_snapshot_id"] == "snap-1"
    archived = {line["product_code"]: line for line in detail["lines"]}
    assert archived["A"]["final_qty"] == 9
    assert archived["A"]["supplier_code"] == "SUP"
    for action in (
        workspace.assign_supplier,
        workspace.export_lines,
        workspace.place_order,
        workspace.submit_to_portal,
    ):
        try:
            action("t1", "s1", "c1", "A")
        except VplError as exc:
            assert exc.code == "NOT_ORDERABLE"
        else:
            raise AssertionError("removed line must reject " + action.__name__)
    assert workspace.assign_supplier("t1", "s1", "c1", "B")["accepted"] is True


def test_failed_refresh_does_not_move_a_touched_line_into_review():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], "snap-1")
    workspace.edit("t1", "s1", "c1", "A", {"final_qty": 9, "supplier_code": "SUP"}, 1, "pm")
    before = workspace.working("t1", "s1", "c1")

    def fail():
        raise RuntimeError("generation failed")

    try:
        workspace.refresh("t1", "s1", "c1", [_line("B", 1)], "snap-2", "pm", before_commit=fail)
    except RuntimeError:
        pass
    else:
        raise AssertionError("refresh should have failed")
    after = workspace.working("t1", "s1", "c1")
    assert after["refresh_id"] == before["refresh_id"]
    assert after["rule_snapshot_id"] == "snap-1"
    assert [line["product_code"] for line in after["lines"]] == ["A"]
    assert after["lines"][0]["final_qty"] == 9
    assert after["removed_manual_review"]["lines"] == []
    assert workspace.history_headers("t1", "s1", limit=None)["total"] == 0


def test_repeated_absence_does_not_duplicate_or_erase_removed_line():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], "snap-1")
    workspace.edit("t1", "s1", "c1", "A", {"final_qty": 9, "supplier_code": "SUP"}, 1, "pm")
    first = workspace.refresh("t1", "s1", "c1", [_line("B", 1)], "snap-2", "pm")
    removed_once = first["working"]["removed_manual_review"]["lines"][0]
    second = workspace.refresh("t1", "s1", "c1", [_line("B", 2)], "snap-3", "pm")
    removed_twice = second["working"]["removed_manual_review"]["lines"]
    assert len(removed_twice) == 1
    assert removed_twice[0]["product_code"] == "A"
    assert removed_twice[0]["final_qty"] == removed_once["final_qty"] == 9
    assert removed_twice[0]["supplier_code"] == "SUP"
    assert removed_twice[0]["row_version"] == removed_once["row_version"]
    assert removed_twice[0]["originating_refresh_id"] == removed_once["originating_refresh_id"]
    active = {line["product_code"] for line in second["working"]["lines"]}
    assert active == {"B"}
    assert "A" not in active


def test_reappearance_restores_touched_line_and_keeps_removal_only_in_history():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], "snap-1")
    workspace.edit("t1", "s1", "c1", "A", {"final_qty": 9, "supplier_code": "SUP", "reviewed_at": "2026-10-19T12:00:00"}, 1, "pm")
    removed = workspace.refresh("t1", "s1", "c1", [], "snap-2", "pm")
    removal_history = workspace.history_detail(removed["history_id"])
    back = workspace.refresh("t1", "s1", "c1", [_line("A", 4)], "snap-3", "pm")
    active = {line["product_code"]: line for line in back["working"]["lines"]}
    assert list(active) == ["A"]
    assert active["A"]["final_qty"] == 9
    assert active["A"]["suggested_qty"] == 4
    assert active["A"]["supplier_code"] == "SUP"
    assert active["A"]["reviewed_at"] == "2026-10-19T12:00:00"
    assert active["A"]["carried_forward"] is True
    assert active["A"]["orderable"] is True
    assert "section" not in active["A"]
    assert back["working"]["removed_manual_review"]["lines"] == []
    assert active["A"]["row_version"] == removed["working"]["removed_manual_review"]["lines"][0]["row_version"] + 1
    still = workspace.history_detail(removed["history_id"])
    assert still["rule_snapshot_id"] == removal_history["rule_snapshot_id"] == "snap-1"
    assert still["lines"][0]["final_qty"] == 9
    assert back["working"]["rule_snapshot_id"] == "snap-3"
    assert workspace.assign_supplier("t1", "s1", "c1", "A")["accepted"] is True


def test_removed_lines_stay_inside_one_store_cycle():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], "snap")
    workspace.open_cycle("t1", "s2", "c2", [_line("A", 5)], "snap")
    workspace.edit("t1", "s1", "c1", "A", {"supplier_code": "SUP"}, 1, "pm")
    workspace.refresh("t1", "s1", "c1", [], "snap-2", "pm")
    home = workspace.working("t1", "s1", "c1")
    other = workspace.working("t1", "s2", "c2")
    assert [line["product_code"] for line in home["removed_manual_review"]["lines"]] == ["A"]
    assert other["removed_manual_review"]["lines"] == []
    assert [line["product_code"] for line in other["lines"]] == ["A"]
    assert other["lines"][0]["supplier_code"] is None


def test_unknown_edit_field_is_rejected():
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 1)], None)
    try:
        workspace.edit("t1", "s1", "c1", "A", {"pending_column": "PurchaseTrans.Pending"}, 1, "pm")
    except VplError as exc:
        assert exc.code == "FIELD"
    else:
        raise AssertionError("unknown field should be rejected")
