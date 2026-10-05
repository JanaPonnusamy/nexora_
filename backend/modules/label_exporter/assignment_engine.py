"""Location-assignment engine for the Label Exporter.

Pure, side-effect-free planning functions — no database, no I/O — so the box
allocation rules are unit-testable in isolation (see
tests/test_label_assignment_engine.py). The repository layer feeds these
functions the current occupancy read from the DB, takes the returned plan, and
commits it in one transaction after re-validating; the frontend only ever
*previews* a plan and never computes the final assignment itself
(spec §AG: backend recalculates and validates).

Business rules preserved from the legacy VB6 app (see memory
`label-exporter-legacy-vb6-rules`):

* TAB  -> 7 products per box, box id ``<LETTER><3-digit>`` e.g. ``A001``.
* SYP  -> one bucket per first-letter-of-name: ``SYP`` + letter (``SYPA``).
* Box numbers are zero-padded to 3 digits (A1 -> A001, A25 -> A025).
* Products are allocated in product-name order.
* The box LETTER is the first letter of each product's *own* name
  (legacy ``let = UCase(Mid(name,1,1))``) — a selection spanning several
  letters is boxed per letter (A-products -> A###, B-products -> B###, ...),
  never dumped under one global letter. A single filter-letter is just the
  common case of one group.

New behaviour (owner-directed, not in the legacy app): Mode 1 fills the last
*partial* box of a letter before opening new boxes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

TAB_BOX_CAPACITY = 7

# Units with a deterministic auto-assignment rule. Everything else
# (LOT / PACK / CREAM / ...) is manual — the engine refuses to invent a
# location for them (spec §R). CAP shares the TAB 7-per-box rule (owner-
# directed, 2026-09) rather than getting its own bucket scheme.
UNIT_TAB = "TAB"
UNIT_CAP = "CAP"
UNIT_SYP = "SYP"

# Units that use the standard 7-per-box, <LETTER><3-digit> numbering.
STANDARD_BOX_UNITS = (UNIT_TAB, UNIT_CAP)


class AssignmentError(ValueError):
    """Raised when a plan cannot be produced (bad unit, empty input, etc.)."""


@dataclass
class Product:
    product_code: str
    product_name: str

    @property
    def first_letter(self) -> str:
        name = (self.product_name or "").strip()
        return name[0].upper() if name else "#"


@dataclass
class Assignment:
    product_code: str
    product_name: str
    box: str
    slot: int  # 1-based position within its box
    mode: str = ""  # per-letter mode that placed it (continue/new_label/single)


@dataclass
class BoxPlan:
    box: str
    existing: int          # products already in the box before this run
    added: int             # products this run puts into the box
    capacity: int | None   # None = no fixed capacity (e.g. SYP bucket)

    @property
    def total(self) -> int:
        return self.existing + self.added


@dataclass
class AssignmentPlan:
    unit: str
    mode: str              # 'continue' | 'new_label' | 'single'
    assignment_type: str   # 'standard_box' | 'single_product_box'
    assignments: list[Assignment] = field(default_factory=list)
    boxes: list[BoxPlan] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "unit": self.unit,
            "mode": self.mode,
            "assignment_type": self.assignment_type,
            "assignments": [
                {
                    "product_code": a.product_code,
                    "product_name": a.product_name,
                    "box": a.box,
                    "slot": a.slot,
                    "mode": a.mode,
                }
                for a in self.assignments
            ],
            "boxes": [
                {
                    "box": b.box,
                    "existing": b.existing,
                    "added": b.added,
                    "total": b.total,
                    "capacity": b.capacity,
                }
                for b in self.boxes
            ],
            "assigned_count": len(self.assignments),
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def format_tab_box(letter: str, number: int) -> str:
    """A, 1 -> 'A001' — legacy 3-digit zero-padded box id."""
    letter = (letter or "").strip().upper()[:1]
    if not letter.isalpha():
        raise AssignmentError(f"Invalid box letter: {letter!r}")
    if number < 1:
        raise AssignmentError(f"Box number must be >= 1, got {number}")
    return f"{letter}{int(number):03d}"


def parse_tab_box(box: str) -> tuple[str, int] | None:
    """'A075' -> ('A', 75). Returns None for anything that is not a
    single-letter + numeric box id (e.g. SYP buckets, blank, malformed)."""
    box = (box or "").strip().upper()
    if len(box) < 2 or not box[0].isalpha():
        return None
    rest = box[1:]
    if not rest.isdigit():
        return None
    return box[0], int(rest)


def _sorted_by_name(products: Iterable[Product]) -> list[Product]:
    return sorted(products, key=lambda p: (p.product_name or "").upper())


def _group_by_letter(
    products: Iterable[Product], fallback: str = ""
) -> dict[str, list[Product]]:
    """Group products by the first letter of their own name (legacy rule:
    box letter = ``UCase(Mid(name,1,1))``). Products whose name does not start
    with a letter fall back to ``fallback`` when that is a letter, otherwise
    they are grouped under their raw initial and ``format_tab_box`` will reject
    them with a clear error."""
    fb = (fallback or "").strip().upper()[:1]
    groups: dict[str, list[Product]] = {}
    for product in products:
        letter = product.first_letter
        if not letter.isalpha() and fb.isalpha():
            letter = fb
        groups.setdefault(letter, []).append(product)
    return groups


def _iter_letter_groups(
    products: Iterable[Product], fallback: str = ""
) -> Iterable[tuple[str, list[Product]]]:
    """Yield (letter, products) groups in A→Z order so a multi-letter plan lays
    its boxes out alphabetically (A001…, B001…, C001…)."""
    groups = _group_by_letter(products, fallback)
    for letter in sorted(groups):
        yield letter, groups[letter]


def letters_in(products: Iterable[Product], fallback: str = "") -> list[str]:
    """Distinct box letters a selection will produce, A→Z (for the UI's
    per-letter mode controls and the service's occupancy fetch)."""
    return sorted(_group_by_letter(products, fallback).keys())


def _highest_box_for_letter(
    letter: str, existing_boxes: dict[str, int]
) -> tuple[int, int]:
    """Return (max_number, occupied_in_max_box) for the given letter across the
    existing occupancy map {box_id: count}. (0, 0) if the letter has no boxes."""
    letter = letter.upper()
    best_num = 0
    best_count = 0
    for box_id, count in existing_boxes.items():
        parsed = parse_tab_box(box_id)
        if not parsed:
            continue
        box_letter, num = parsed
        if box_letter != letter:
            continue
        if num > best_num:
            best_num = num
            best_count = int(count or 0)
    return best_num, best_count


# --------------------------------------------------------------------------
# TAB — Mode 2: New Label for the entire letter (ignore existing locations)
# --------------------------------------------------------------------------

def plan_new_label(
    letter: str,
    products: Iterable[Product],
    capacity: int = TAB_BOX_CAPACITY,
    start_number: int = 1,
    unit: str = UNIT_TAB,
) -> AssignmentPlan:
    """Fresh box sequence, 7 per box, ignoring any existing occupancy
    (spec §O). Products are sorted by name, then chunked."""
    ordered = _sorted_by_name(products)
    if not ordered:
        raise AssignmentError("No products to assign")
    plan = AssignmentPlan(unit=unit, mode="new_label", assignment_type="standard_box")
    for index, product in enumerate(ordered):
        box_index, slot = divmod(index, capacity)
        box = format_tab_box(letter, start_number + box_index)
        plan.assignments.append(
            Assignment(product.product_code, product.product_name, box, slot + 1)
        )
    plan.boxes = _summarise_boxes(plan.assignments, existing={}, capacity=capacity)
    return plan


# --------------------------------------------------------------------------
# TAB — Mode 1: Continue existing locations (fill the last partial box first)
# --------------------------------------------------------------------------

def plan_continue(
    letter: str,
    products: Iterable[Product],
    existing_boxes: dict[str, int],
    capacity: int = TAB_BOX_CAPACITY,
    unit: str = UNIT_TAB,
) -> AssignmentPlan:
    """Fill the last partial box of ``letter`` to capacity, then open new boxes
    (spec §N). ``existing_boxes`` maps box id -> current product count, read
    live from the DB. A box already at capacity is never modified."""
    ordered = _sorted_by_name(products)
    if not ordered:
        raise AssignmentError("No products to assign")

    max_num, occupied = _highest_box_for_letter(letter, existing_boxes)
    plan = AssignmentPlan(unit=unit, mode="continue", assignment_type="standard_box")

    queue = list(ordered)
    existing_for_summary: dict[str, int] = {}

    # 1) top up the last partial box
    if max_num >= 1 and occupied < capacity:
        box = format_tab_box(letter, max_num)
        free = capacity - occupied
        slot = occupied
        existing_for_summary[box] = occupied
        while queue and free > 0:
            product = queue.pop(0)
            slot += 1
            plan.assignments.append(
                Assignment(product.product_code, product.product_name, box, slot)
            )
            free -= 1

    # 2) open fresh boxes for the remainder
    next_num = max_num + 1 if max_num >= 1 else 1
    for index, product in enumerate(queue):
        box_index, slot = divmod(index, capacity)
        box = format_tab_box(letter, next_num + box_index)
        plan.assignments.append(
            Assignment(product.product_code, product.product_name, box, slot + 1)
        )

    plan.boxes = _summarise_boxes(plan.assignments, existing_for_summary, capacity)
    return plan


# --------------------------------------------------------------------------
# SYP — one bucket per first letter of product name (SYPA, SYPB, ...)
# --------------------------------------------------------------------------

def plan_syp(products: Iterable[Product]) -> AssignmentPlan:
    """SYP products group into ``SYP`` + first-letter buckets (spec §Q).
    There is no per-box capacity — every A-product shares SYPA."""
    ordered = _sorted_by_name(products)
    if not ordered:
        raise AssignmentError("No products to assign")
    plan = AssignmentPlan(unit=UNIT_SYP, mode="new_label", assignment_type="standard_box")
    slot_by_box: dict[str, int] = {}
    for product in ordered:
        box = f"SYP{product.first_letter}"
        slot_by_box[box] = slot_by_box.get(box, 0) + 1
        plan.assignments.append(
            Assignment(product.product_code, product.product_name, box, slot_by_box[box])
        )
    plan.boxes = _summarise_boxes(plan.assignments, existing={}, capacity=None)
    return plan


# --------------------------------------------------------------------------
# Single product box — one product, one box (spec §S)
# --------------------------------------------------------------------------

def plan_single_boxes(
    letter: str,
    products: Iterable[Product],
    existing_boxes: dict[str, int],
) -> AssignmentPlan:
    """Each product gets its own box; box numbers continue after the highest
    existing box for the letter. Not squeezed through the 7-per-box rule."""
    ordered = _sorted_by_name(products)
    if not ordered:
        raise AssignmentError("No products to assign")
    max_num, _ = _highest_box_for_letter(letter, existing_boxes)
    plan = AssignmentPlan(unit=UNIT_TAB, mode="single", assignment_type="single_product_box")
    next_num = max_num + 1 if max_num >= 1 else 1
    for index, product in enumerate(ordered):
        box = format_tab_box(letter, next_num + index)
        plan.assignments.append(
            Assignment(product.product_code, product.product_name, box, 1)
        )
    plan.boxes = _summarise_boxes(plan.assignments, existing={}, capacity=1)
    return plan


# --------------------------------------------------------------------------
# Multi-letter orchestration — each letter runs its OWN mode (Continue / New
# from 1 / Single product box). This is what the drawer's per-letter dropdowns
# drive, and it is also the correct single-letter path (one group).
# --------------------------------------------------------------------------

# Per-letter mode names accepted in a letter spec.
LETTER_MODE_CONTINUE = "continue"
LETTER_MODE_NEW = "new_label"
LETTER_MODE_SINGLE = "single"
_VALID_LETTER_MODES = {LETTER_MODE_CONTINUE, LETTER_MODE_NEW, LETTER_MODE_SINGLE}


def plan_by_letter(
    products: Iterable[Product],
    letter_specs: dict[str, dict] | None = None,
    existing_boxes: dict[str, int] | None = None,
    *,
    default_mode: str = LETTER_MODE_CONTINUE,
    default_start: int = 1,
    unit: str = UNIT_TAB,
    capacity: int = TAB_BOX_CAPACITY,
    fallback_letter: str = "",
) -> AssignmentPlan:
    """Assign TAB/CAP products letter-by-letter, each letter applying the mode
    chosen for it (``letter_specs[LETTER] = {"mode": ..., "start_number": ...}``).
    Letters without a spec use ``default_mode`` / ``default_start``. Delegates
    each group to the single-letter planners and merges the results, so one box
    can never span two letters. ``existing_boxes`` is the full occupancy map
    (all letters) read live from the DB."""
    ordered = _sorted_by_name(products)
    if not ordered:
        raise AssignmentError("No products to assign")
    specs = letter_specs or {}
    occ = existing_boxes or {}

    master = AssignmentPlan(unit=unit, mode=default_mode, assignment_type="standard_box")
    modes_used: set[str] = set()
    types_used: set[str] = set()

    for grp_letter, group in _iter_letter_groups(ordered, fallback=fallback_letter):
        spec = specs.get(grp_letter) or {}
        mode = (spec.get("mode") or default_mode or LETTER_MODE_CONTINUE).strip()
        if mode not in _VALID_LETTER_MODES:
            raise AssignmentError(f"Invalid mode {mode!r} for letter {grp_letter}")
        start = int(spec.get("start_number") or default_start or 1)

        if mode == LETTER_MODE_SINGLE:
            sub = plan_single_boxes(grp_letter, group, occ)
        elif mode == LETTER_MODE_NEW:
            sub = plan_new_label(grp_letter, group, capacity=capacity, start_number=start, unit=unit)
        else:
            sub = plan_continue(grp_letter, group, occ, capacity=capacity, unit=unit)

        for assignment in sub.assignments:
            assignment.mode = mode  # per-row mode for an accurate audit trail
        master.assignments.extend(sub.assignments)
        master.boxes.extend(sub.boxes)
        modes_used.add(mode)
        types_used.add(sub.assignment_type)

    # A uniform selection keeps its single mode/type label; a mixed one is tagged
    # 'mixed' / 'standard_box' (each box still carries its own capacity).
    master.mode = next(iter(modes_used)) if len(modes_used) == 1 else "mixed"
    master.assignment_type = (
        "single_product_box" if types_used == {"single_product_box"} else "standard_box"
    )
    return master


def _summarise_boxes(
    assignments: list[Assignment], existing: dict[str, int], capacity: int | None
) -> list[BoxPlan]:
    added: dict[str, int] = {}
    order: list[str] = []
    for a in assignments:
        if a.box not in added:
            added[a.box] = 0
            order.append(a.box)
        added[a.box] += 1
    return [
        BoxPlan(box=box, existing=int(existing.get(box, 0)), added=added[box], capacity=capacity)
        for box in order
    ]


def validate_plan(plan: AssignmentPlan) -> None:
    """Backend guard rails re-checked before commit (spec §AF): a TAB box may
    never exceed 7, a single-product box holds exactly one, and no product may
    be assigned twice in one plan."""
    seen: set[str] = set()
    for a in plan.assignments:
        if a.product_code in seen:
            raise AssignmentError(f"Product {a.product_code} assigned twice in one plan")
        seen.add(a.product_code)
    for box in plan.boxes:
        if box.capacity is not None and box.total > box.capacity:
            raise AssignmentError(
                f"Box {box.box} would hold {box.total} > capacity {box.capacity}"
            )
        if plan.assignment_type == "single_product_box" and box.added != 1:
            raise AssignmentError(f"Single-product box {box.box} has {box.added} products")
