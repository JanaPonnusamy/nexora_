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

New behaviour (owner-directed, not in the legacy app): Mode 1 fills the last
*partial* box of a letter before opening new boxes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

TAB_BOX_CAPACITY = 7

# Units with a deterministic auto-assignment rule. Everything else
# (CAP / LOT / PACK / CREAM / ...) is manual — the engine refuses to invent a
# location for them (spec §R).
UNIT_TAB = "TAB"
UNIT_SYP = "SYP"


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
) -> AssignmentPlan:
    """Fresh box sequence, 7 per box, ignoring any existing occupancy
    (spec §O). Products are sorted by name, then chunked."""
    ordered = _sorted_by_name(products)
    if not ordered:
        raise AssignmentError("No products to assign")
    plan = AssignmentPlan(unit=UNIT_TAB, mode="new_label", assignment_type="standard_box")
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
) -> AssignmentPlan:
    """Fill the last partial box of ``letter`` to capacity, then open new boxes
    (spec §N). ``existing_boxes`` maps box id -> current product count, read
    live from the DB. A box already at capacity is never modified."""
    ordered = _sorted_by_name(products)
    if not ordered:
        raise AssignmentError("No products to assign")

    max_num, occupied = _highest_box_for_letter(letter, existing_boxes)
    plan = AssignmentPlan(unit=UNIT_TAB, mode="continue", assignment_type="standard_box")

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
