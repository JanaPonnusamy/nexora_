"""Claude-owned edge-case tests for Phase 2 VPL history.

Independent of tests/test_vpl_history.py (Cursor-owned; not edited here).
No database, no decision engine. These exercise cases the existing suite
does not cover, found while reviewing vpl_history.py for
PHASE_2_CLAUDE_REVIEW.md.
"""

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


def test_touched_line_dropped_from_next_generation_survives_only_in_history():
    """Cursor changed this expectation on 2026-10-19 because the user
    approved Option A in conversation, not because an approval artifact
    was already in the repo. A manually-touched line whose product_code
    is absent from the new generated list is not an active orderable
    line. It stays visible in removed_manual_review. The prior working
    set, including this line, is still archived verbatim."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5), _line("B", 2)], "snap-1")
    workspace.edit("t1", "s1", "c1", "A", {"final_qty": 9, "supplier_code": "SUP"}, 1, "pm")

    # New generation omits "A" entirely (e.g. product fell out of eligibility).
    result = workspace.refresh("t1", "s1", "c1", [_line("B", 3)], "snap-2", "pm")

    by_code = {line["product_code"]: line for line in result["working"]["lines"]}
    assert "A" not in by_code, "touched line A is not an active orderable line"
    assert "B" in by_code
    removed = {
        line["product_code"]: line
        for line in result["working"]["removed_manual_review"]["lines"]
    }
    assert removed["A"]["final_qty"] == 9
    assert removed["A"]["supplier_code"] == "SUP"
    assert removed["A"]["orderable"] is False
    assert result["working"]["removed_manual_review"]["section"] == (
        "Removed from Current Suggestions — Manual Review"
    )

    detail = workspace.history_detail(result["history_id"])
    archived = {line["product_code"]: line for line in detail["lines"]}
    assert archived["A"]["final_qty"] == 9
    assert archived["A"]["supplier_code"] == "SUP"


def test_concurrent_refreshes_on_different_stores_do_not_interleave():
    """Two stores refreshing around the same time must not see each
    other's working set or history. Exercises the full (tenant, store,
    cycle) key more aggressively than the existing suite's two-store test
    by interleaving edits and refreshes across both stores."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 1)], "snap")
    workspace.open_cycle("t1", "s2", "c2", [_line("A", 100)], "snap")

    workspace.edit("t1", "s1", "c1", "A", {"final_qty": 7}, 1, "pm-1")
    workspace.edit("t1", "s2", "c2", "A", {"final_qty": 777}, 1, "pm-2")

    result_s1 = workspace.refresh("t1", "s1", "c1", [_line("A", 2)], "snap-2", "pm-1")
    result_s2 = workspace.refresh("t1", "s2", "c2", [_line("A", 200)], "snap-2", "pm-2")

    s1_lines = {line["product_code"]: line for line in result_s1["working"]["lines"]}
    s2_lines = {line["product_code"]: line for line in result_s2["working"]["lines"]}
    assert s1_lines["A"]["final_qty"] == 7
    assert s2_lines["A"]["final_qty"] == 777

    s1_history = workspace.history_headers("t1", "s1", limit=None)
    s2_history = workspace.history_headers("t1", "s2", limit=None)
    assert s1_history["total"] == 1
    assert s2_history["total"] == 1
    assert s1_history["headers"][0]["history_id"] != s2_history["headers"][0]["history_id"]


def test_untouched_line_row_version_advances_across_refresh():
    """Cursor fixed the HIGH finding: an untouched line's row_version now
    increments on refresh, so a client still holding the pre-refresh version
    gets VERSION instead of overwriting the new suggestion."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], "snap-1")
    before = workspace.working("t1", "s1", "c1")
    pre_refresh_version = before["lines"][0]["row_version"]

    workspace.refresh("t1", "s1", "c1", [_line("A", 9)], "snap-2", "pm")
    after_refresh = workspace.working("t1", "s1", "c1")

    assert after_refresh["lines"][0]["row_version"] == pre_refresh_version + 1
    assert after_refresh["lines"][0]["final_qty"] == 9
    try:
        workspace.edit("t1", "s1", "c1", "A", {"final_qty": 42}, pre_refresh_version, "late-editor")
    except VplConflict as exc:
        assert exc.code == "VERSION"
    else:
        raise AssertionError("a pre-refresh row_version must not overwrite the new suggestion")


def test_repeated_refreshes_never_reset_or_reuse_an_untouched_lines_version():
    """Point 8 of Cursor's fix instructions: across many repeated refreshes
    of the same untouched logical line, row_version must strictly increase
    every time, never reset to 1 and never repeat a prior value. Verifies
    the fix in vpl_history.py:122-124 generalizes past a single refresh."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 1)], "snap")
    versions = [workspace.working("t1", "s1", "c1")["lines"][0]["row_version"]]
    for step in range(5):
        workspace.refresh("t1", "s1", "c1", [_line("A", step + 2)], "snap", "pm")
        versions.append(workspace.working("t1", "s1", "c1")["lines"][0]["row_version"])
    assert len(set(versions)) == len(versions), "no version value repeated: " + str(versions)
    assert all(versions[i] < versions[i + 1] for i in range(len(versions) - 1)), (
        "version must strictly increase every refresh: " + str(versions)
    )
    # The oldest version is now conflict-stale no matter how far back it is.
    try:
        workspace.edit("t1", "s1", "c1", "A", {"final_qty": 999}, versions[0], "very-late-editor")
    except VplConflict as exc:
        assert exc.code == "VERSION"
    else:
        raise AssertionError("a version from several refreshes ago must still conflict")


def test_refresh_with_no_prior_touched_lines_carries_nothing():
    """Sanity check on the untouched-line path across a refresh with
    multiple untouched lines and a line dropped at the same time -- the
    existing suite only tests a mix of touched+untouched; this isolates
    the all-untouched case plus a simultaneous drop."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 1), _line("B", 2), _line("C", 3)], "snap-1")
    result = workspace.refresh("t1", "s1", "c1", [_line("A", 10), _line("B", 20)], "snap-2", "pm")
    by_code = {line["product_code"]: line for line in result["working"]["lines"]}
    assert by_code["A"]["final_qty"] == 10
    assert by_code["A"]["carried_forward"] is False
    assert by_code["B"]["final_qty"] == 20
    assert "C" not in by_code
    detail = workspace.history_detail(result["history_id"])
    archived_codes = {line["product_code"] for line in detail["lines"]}
    assert archived_codes == {"A", "B", "C"}, "all three prior lines, including C, are archived"


def test_duplicate_line_in_open_cycle_itself_is_rejected():
    """The existing suite tests duplicates in `refresh()`'s generated
    list. open_cycle() goes through the same `_index` helper and must
    reject a duplicate the same way on the very first generation, before
    any working set exists at all."""
    workspace = VplWorkspace()
    try:
        workspace.open_cycle("t1", "s1", "c1", [_line("A", 1), _line("A", 2)], "snap")
    except VplConflict as exc:
        assert exc.code == "DUPLICATE_LINE"
    else:
        raise AssertionError("duplicate product code on first open should conflict")
    try:
        workspace.working("t1", "s1", "c1")
    except VplError as exc:
        assert exc.code == "ABSENT"
    else:
        raise AssertionError("a rejected open_cycle must not leave a working set behind")


def test_missing_product_code_on_a_generated_line_is_rejected():
    """_index raises IDENTITY when a line has no product_code. Not
    exercised by the existing suite at all."""
    workspace = VplWorkspace()
    try:
        workspace.open_cycle("t1", "s1", "c1", [{"suggested_qty": 5}], "snap")
    except VplError as exc:
        assert exc.code == "IDENTITY"
    else:
        raise AssertionError("a line without product_code should be rejected")


# ---------------------------------------------------------------------------
# 2026-10-20 temporary-implementer pass: identity-key and skip/removal
# regression tests. Corrects the contradiction flagged in
# PHASE_2_CLAUDE_REVIEW.md -- the real procurement_order_items table keys on
# (refresh_id, product_id), not product_code; and skip_item() setting
# reviewed_at must not be misread as a manual edit.
# ---------------------------------------------------------------------------


def test_line_with_product_id_and_no_product_code_is_accepted_and_findable():
    """A null/missing product_code must not drop or reject a line when a
    product_id is present -- the real table allows a null product_code."""
    workspace = VplWorkspace()
    opened = workspace.open_cycle(
        "t1", "s1", "c1",
        [{"product_id": 501, "product_code": None, "suggested_qty": 5, "final_qty": 5}],
        "snap",
    )
    assert len(opened["lines"]) == 1
    assert opened["lines"][0]["product_id"] == 501
    assert opened["lines"][0]["product_code"] is None


def test_distinct_products_sharing_a_product_code_are_never_merged():
    """Two lines with the same product_code but different product_id are
    distinct working lines -- a code collision alone must not merge or
    reject them, unlike the old product_code-only index."""
    workspace = VplWorkspace()
    opened = workspace.open_cycle(
        "t1", "s1", "c1",
        [
            {"product_id": 1, "product_code": "DUP", "suggested_qty": 5, "final_qty": 5},
            {"product_id": 2, "product_code": "DUP", "suggested_qty": 9, "final_qty": 9},
        ],
        "snap",
    )
    by_id = {line["product_id"]: line for line in opened["lines"]}
    assert len(by_id) == 2
    assert by_id[1]["final_qty"] == 5
    assert by_id[2]["final_qty"] == 9


def test_product_code_changing_across_refresh_does_not_lose_the_line():
    """Identity follows product_id. A changed product_code on the same
    product_id across a refresh must still be recognized as the same
    line, not dropped and re-created."""
    workspace = VplWorkspace()
    workspace.open_cycle(
        "t1", "s1", "c1",
        [{"product_id": 77, "product_code": "OLD-CODE", "suggested_qty": 5, "final_qty": 5}],
        "snap-1",
    )
    workspace.edit(
        "t1", "s1", "c1", "OLD-CODE",
        {"final_qty": 9, "supplier_code": "SUP"}, 1, "pm",
    )
    result = workspace.refresh(
        "t1", "s1", "c1",
        [{"product_id": 77, "product_code": "NEW-CODE", "suggested_qty": 4, "final_qty": 4}],
        "snap-2", "pm",
    )
    lines = result["working"]["lines"]
    assert len(lines) == 1
    assert lines[0]["product_id"] == 77
    assert lines[0]["final_qty"] == 9, "manual edit must survive the product_code rename"
    assert lines[0]["supplier_code"] == "SUP"
    assert lines[0]["carried_forward"] is True


def test_stable_source_item_identity_resolves_edit_by_code_when_unambiguous():
    """edit()/_guard_orderable() still take product_code from the router.
    When only one line has that code, the lookup must still work after
    the product_id-based reindex."""
    workspace = VplWorkspace()
    workspace.open_cycle(
        "t1", "s1", "c1",
        [{"product_id": 9, "product_code": "P9", "suggested_qty": 1, "final_qty": 1}],
        "snap",
    )
    edited = workspace.edit("t1", "s1", "c1", "P9", {"final_qty": 3}, 1, "pm")
    assert edited["final_qty"] == 3
    assert workspace.assign_supplier("t1", "s1", "c1", "P9")["accepted"] is True


def test_skip_with_reviewed_at_but_no_manual_override_is_not_manual_review():
    """skip_item()-shaped line: item_status='skipped', reviewed_at set,
    manual_override False, no supplier, no rare_confirmed. Dropping out
    of the next generation must NOT route it into removed_manual_review
    -- a skip alone is not a manual edit worth preserving there."""
    workspace = VplWorkspace()
    workspace.open_cycle(
        "t1", "s1", "c1",
        [_line("A", 5, item_status="skipped", reviewed_at="2026-10-20T10:00:00", final_qty=0), _line("B", 2)],
        "snap-1",
    )
    result = workspace.refresh("t1", "s1", "c1", [_line("B", 3)], "snap-2", "pm")
    active = {line["product_code"]: line for line in result["working"]["lines"]}
    assert "A" not in active
    removed = {line["product_code"]: line for line in result["working"]["removed_manual_review"]["lines"]}
    assert "A" not in removed, "a bare skip must not land in manual review"
    detail = workspace.history_detail(result["history_id"])
    archived = {line["product_code"] for line in detail["lines"]}
    assert "A" in archived, "the skipped line is still archived in history, just not in manual review"


def test_skip_combined_with_manual_override_still_counts_as_touched():
    """A line that was both skipped AND has a genuine manual_override
    (e.g. the PM set a final qty before skipping, or skip_item ran after
    an earlier override) must still be treated as touched -- the skip
    does not erase the prior manual-edit signal."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5), _line("B", 2)], "snap-1")
    workspace.edit("t1", "s1", "c1", "A", {"final_qty": 9}, 1, "pm")
    # Now simulate skip_item() running on top of the already-overridden line.
    body = workspace.working("t1", "s1", "c1")
    line_a = next(line for line in body["lines"] if line["product_code"] == "A")
    workspace.edit(
        "t1", "s1", "c1", "A",
        {"final_qty": 0, "reason_code": "skipped"}, line_a["row_version"], "pm",
    )
    result = workspace.refresh("t1", "s1", "c1", [_line("B", 3)], "snap-2", "pm")
    removed = {line["product_code"]: line for line in result["working"]["removed_manual_review"]["lines"]}
    assert "A" in removed, "manual_override from the edit must still route this line to manual review"


def test_skip_combined_with_supplier_assignment_still_counts_as_touched():
    """A skipped line that nonetheless carries a live supplier_code must
    still be preserved in manual review, not silently dropped -- supplier
    assignments must never be lost."""
    workspace = VplWorkspace()
    workspace.open_cycle(
        "t1", "s1", "c1",
        [_line("A", 5, item_status="skipped", reviewed_at="2026-10-20T10:00:00", supplier_code="SUP"), _line("B", 2)],
        "snap-1",
    )
    result = workspace.refresh("t1", "s1", "c1", [_line("B", 3)], "snap-2", "pm")
    removed = {line["product_code"]: line for line in result["working"]["removed_manual_review"]["lines"]}
    assert "A" in removed
    assert removed["A"]["supplier_code"] == "SUP"


def test_stale_row_version_rejected_in_existing_in_memory_service():
    """Restates the existing stale-write protection explicitly under the
    'regression tests' requirement -- expected_version must match exactly
    or VplConflict/VERSION is raised, leaving the line unchanged."""
    workspace = VplWorkspace()
    workspace.open_cycle("t1", "s1", "c1", [_line("A", 5)], "snap")
    try:
        workspace.edit("t1", "s1", "c1", "A", {"final_qty": 99}, 999, "pm")
    except VplConflict as exc:
        assert exc.code == "VERSION"
    else:
        raise AssertionError("a wildly stale version must conflict")
    unchanged = workspace.working("t1", "s1", "c1")["lines"][0]
    assert unchanged["final_qty"] == 5


# ---------------------------------------------------------------------------
# 2026-10-20 (fix pass): regression tests for the confirmed _public() crash
# on a null product_code once a second line exists. Each of these calls the
# real read path (working()/open_cycle()'s own return) with MORE THAN ONE
# line present, not just open_cycle() alone -- the prior gap was a test that
# only ever had one line in the working set, so the sort comparator (which
# only runs when there is something to compare against) never fired.
# ---------------------------------------------------------------------------


def _pid_code(line):
    return (line["product_id"], line["product_code"])


def test_one_null_coded_line_and_one_string_coded_line_reads_without_crashing():
    workspace = VplWorkspace()
    opened = workspace.open_cycle(
        "t1", "s1", "c1",
        [
            {"product_id": 1, "product_code": None, "suggested_qty": 5, "final_qty": 5},
            {"product_id": 2, "product_code": "B", "suggested_qty": 3, "final_qty": 3},
        ],
        "snap",
    )
    assert {_pid_code(line) for line in opened["lines"]} == {(1, None), (2, "B")}
    read_back = workspace.working("t1", "s1", "c1")
    assert {_pid_code(line) for line in read_back["lines"]} == {(1, None), (2, "B")}
    # Deterministic: null-coded lines sort after string-coded lines.
    assert read_back["lines"][0]["product_code"] == "B"
    assert read_back["lines"][1]["product_code"] is None


def test_two_null_coded_lines_with_distinct_product_ids_read_without_crashing():
    workspace = VplWorkspace()
    opened = workspace.open_cycle(
        "t1", "s1", "c1",
        [
            {"product_id": 10, "product_code": None, "suggested_qty": 1, "final_qty": 1},
            {"product_id": 20, "product_code": None, "suggested_qty": 2, "final_qty": 2},
        ],
        "snap",
    )
    assert {_pid_code(line) for line in opened["lines"]} == {(10, None), (20, None)}
    read_back = workspace.working("t1", "s1", "c1")
    identities = {_pid_code(line) for line in read_back["lines"]}
    assert identities == {(10, None), (20, None)}
    # Both lines must be present and distinguishable by product_id alone.
    assert len(read_back["lines"]) == 2
    # Deterministic across repeated reads.
    second_read = workspace.working("t1", "s1", "c1")
    assert [line["product_id"] for line in read_back["lines"]] == [line["product_id"] for line in second_read["lines"]]


def test_two_distinct_product_ids_sharing_one_product_code_read_without_crashing():
    workspace = VplWorkspace()
    opened = workspace.open_cycle(
        "t1", "s1", "c1",
        [
            {"product_id": 5, "product_code": "DUP", "suggested_qty": 1, "final_qty": 1},
            {"product_id": 3, "product_code": "DUP", "suggested_qty": 2, "final_qty": 2},
        ],
        "snap",
    )
    identities = {_pid_code(line) for line in opened["lines"]}
    assert identities == {(5, "DUP"), (3, "DUP")}, "both lines kept as distinct products despite the shared code"
    read_back = workspace.working("t1", "s1", "c1")
    assert {_pid_code(line) for line in read_back["lines"]} == identities


def test_repeated_reads_of_a_mixed_null_and_duplicate_coded_set_are_deterministically_ordered():
    """Combines null codes and a duplicate code in one working set and
    reads it back multiple times -- the exact ordering must not vary
    between reads (no reliance on dict/set iteration order)."""
    workspace = VplWorkspace()
    workspace.open_cycle(
        "t1", "s1", "c1",
        [
            {"product_id": 1, "product_code": None, "suggested_qty": 1, "final_qty": 1},
            {"product_id": 2, "product_code": "DUP", "suggested_qty": 2, "final_qty": 2},
            {"product_id": 3, "product_code": "DUP", "suggested_qty": 3, "final_qty": 3},
            {"product_id": 4, "product_code": None, "suggested_qty": 4, "final_qty": 4},
        ],
        "snap",
    )
    orderings = []
    for _ in range(5):
        read_back = workspace.working("t1", "s1", "c1")
        assert len(read_back["lines"]) == 4
        orderings.append([line["product_id"] for line in read_back["lines"]])
    assert all(order == orderings[0] for order in orderings), (
        "repeated reads must return the same order every time: " + str(orderings)
    )
    # Null-coded lines must sort after the string-coded (DUP) lines.
    first = orderings[0]
    dup_positions = [first.index(pid) for pid in (2, 3)]
    null_positions = [first.index(pid) for pid in (1, 4)]
    assert max(dup_positions) < min(null_positions)


def test_removed_manual_review_section_also_survives_null_coded_lines():
    """The same crash existed in the removed_manual_review sort. A
    touched null-coded line dropped from the next generation must still
    read back correctly alongside another removed line."""
    workspace = VplWorkspace()
    workspace.open_cycle(
        "t1", "s1", "c1",
        [
            {"product_id": 1, "product_code": None, "suggested_qty": 5, "final_qty": 5},
            {"product_id": 2, "product_code": "B", "suggested_qty": 2, "final_qty": 2},
        ],
        "snap-1",
    )
    workspace.edit("t1", "s1", "c1", None, {"final_qty": 9, "supplier_code": "SUP"}, 1, "pm")
    workspace.edit("t1", "s1", "c1", "B", {"final_qty": 7, "supplier_code": "SUP2"}, 1, "pm")
    result = workspace.refresh("t1", "s1", "c1", [], "snap-2", "pm")
    removed = result["working"]["removed_manual_review"]["lines"]
    assert len(removed) == 2
    assert {_pid_code(line) for line in removed} == {(1, None), (2, "B")}


def test_two_null_coded_lines_coexist_distinct_in_removed_manual_review():
    """Review condition 1 (2026-10-20 independent re-verification,
    'APPROVE WITH CONDITIONS'): two distinct product_ids, both with
    product_code=None, must coexist in removed_manual_review without
    merging, dropping, or losing either line's own final_qty/supplier_code.
    product_code=None cannot disambiguate between them for an edit (see
    _resolve_by_code -- a second AMBIGUOUS edit attempt is asserted
    below), so each line is given its manual_override/supplier_code
    directly in the open_cycle payload, the same shape the real
    workspace_repository writers would have already applied to a live
    row before this in-memory model ever sees it; this does not invent a
    new field or alter production behavior, it only avoids routing
    through the one lookup path that is correctly ambiguous for this
    case."""
    workspace = VplWorkspace()
    workspace.open_cycle(
        "t1", "s1", "c1",
        [
            {
                "product_id": 1, "product_code": None,
                "suggested_qty": 5, "final_qty": 9,
                "manual_override": True, "supplier_code": "SUP1",
            },
            {
                "product_id": 3, "product_code": None,
                "suggested_qty": 1, "final_qty": 4,
                "manual_override": True, "supplier_code": "SUP3",
            },
            {"product_id": 2, "product_code": "B", "suggested_qty": 2, "final_qty": 2},
        ],
        "snap-1",
    )

    # product_code=None is ambiguous the moment a second null-coded line
    # exists -- confirmed fail-closed, not a silent pick of either line.
    try:
        workspace.edit("t1", "s1", "c1", None, {"final_qty": 1}, 1, "pm")
    except VplError as exc:
        assert exc.code == "AMBIGUOUS"
    else:
        raise AssertionError("edit by product_code=None must fail closed once two null-coded lines coexist")

    result = workspace.refresh(
        "t1", "s1", "c1",
        [{"product_id": 2, "product_code": "B", "suggested_qty": 3, "final_qty": 3}],
        "snap-2", "pm",
    )
    removed = {line["product_id"]: line for line in result["working"]["removed_manual_review"]["lines"]}

    # Both identities present and distinct -- neither merged nor dropped.
    assert set(removed) == {1, 3}
    assert all(line["product_code"] is None for line in removed.values())

    # Each line keeps its own final_qty and supplier_code, not the other's.
    assert removed[1]["final_qty"] == 9
    assert removed[1]["supplier_code"] == "SUP1"
    assert removed[3]["final_qty"] == 4
    assert removed[3]["supplier_code"] == "SUP3"

    # Repeated reads produce deterministic ordering.
    first_order = [line["product_id"] for line in workspace.working("t1", "s1", "c1")["removed_manual_review"]["lines"]]
    for _ in range(4):
        next_order = [line["product_id"] for line in workspace.working("t1", "s1", "c1")["removed_manual_review"]["lines"]]
        assert next_order == first_order

    # No automatic assignment, export, ordering, or portal submission is
    # possible for either removed line.
    for product_id in (1, 3):
        for action in (
            workspace.assign_supplier,
            workspace.export_lines,
            workspace.place_order,
            workspace.submit_to_portal,
        ):
            try:
                # Both removed lines share product_code=None, so the
                # product_code-only action methods are themselves
                # ambiguous for this pair -- either AMBIGUOUS (fails
                # closed before reaching the orderable check) or
                # NOT_ORDERABLE is acceptable; a successful "accepted"
                # action is not.
                action("t1", "s1", "c1", None)
            except VplError as exc:
                assert exc.code in ("AMBIGUOUS", "NOT_ORDERABLE")
            else:
                raise AssertionError(
                    action.__name__ + " must not succeed for a removed manual-review line (product_id " + str(product_id) + ")"
                )

    # The surviving string-coded line is unaffected and still orderable.
    assert workspace.assign_supplier("t1", "s1", "c1", "B")["accepted"] is True
