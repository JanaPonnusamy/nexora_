"""D3c — rare-mover confirmation enforcement (owner-approved discrete field,
2026-10-21). See AUTONOMOUS_WORK_CONTROL.md / PHASE_2_CLAUDE_REVIEW.md D3/D3c
for the decision record.

Confirmation is a plain bit on procurement_order_items (rare_confirmed /
rare_confirmed_by / rare_confirmed_at), added by 0028_rare_mover_confirmation.sql
(NOT APPLIED). Scoping to "current cycle only" is satisfied for free: each
cycle/refresh mints a fresh order_item row (UNIQUE (refresh_id, product_id)),
so there is no stale cross-cycle row to misread — a new cycle's row always
starts unconfirmed.

Feature-gated behind PROCUREMENT_RARE_MOVER_ENFORCEMENT (default "0" / off):
0028 is not applied yet, so the rare_confirmed column does not exist on the
live table and no PM can ever set it — enforcing unconditionally today would
permanently block every rare-mover line from assignment/export in production
with no way to unblock it. Flip the env var on only after 0028 is applied.
"""

import os

from fastapi import HTTPException

from modules.procurement.decision_rules import INCLUDED_RARE_MOVER_TOPUP

RARE_MOVER_REASON_CODES = {INCLUDED_RARE_MOVER_TOPUP}


def enforcement_enabled():
    return os.environ.get("PROCUREMENT_RARE_MOVER_ENFORCEMENT", "0") == "1"


def is_rare_mover(item):
    return item.get("reason_code") in RARE_MOVER_REASON_CODES


def require_confirmed(item):
    """Raise 409 if this item is a rare mover requiring confirmation and the
    enforcement flag is on and it has not been confirmed. No-op (not even a
    reason_code check) when the flag is off, so this is safe to call from
    every assignment/export entry point unconditionally."""
    if not enforcement_enabled():
        return
    if not is_rare_mover(item):
        return
    if not item.get("rare_confirmed"):
        raise HTTPException(
            status_code=409,
            detail="Rare-mover item requires PM confirmation before assignment or export",
        )
