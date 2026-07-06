"""VPL comparison service — runtime only, results never persisted.

Validates that both snapshots exist for the tenant and belong to the same
cycle (a comparison is between two refreshes of one cycle), then returns an
in-memory comparison produced entirely by the read-only repository query. No
comparison entity, table or history is involved.
"""

from fastapi import HTTPException

from modules.procurement import compare_repository as repo
from modules.procurement import vpl_repository as vpl_repo

_VALID_ACTIONS = {"Added", "Removed", "Increased", "Decreased", "NoChange"}


def compare(tenant_id, source_vpl_id, target_vpl_id,
            changed_only=False, action_filter=None,
            search=None, page=1, page_size=20):
    if source_vpl_id == target_vpl_id:
        raise HTTPException(
            status_code=400,
            detail="source_vpl_id and target_vpl_id must differ",
        )

    source = vpl_repo.get_vpl(tenant_id, source_vpl_id)
    if not source:
        raise HTTPException(status_code=404, detail="source VPL not found")
    target = vpl_repo.get_vpl(tenant_id, target_vpl_id)
    if not target:
        raise HTTPException(status_code=404, detail="target VPL not found")

    if source["cycle_id"] != target["cycle_id"]:
        raise HTTPException(
            status_code=400,
            detail="VPLs must belong to the same cycle",
        )

    normalized_action = None
    if action_filter:
        normalized_action = action_filter.strip().capitalize()
        # accept 'NoChange' which capitalize() would mangle
        for valid in _VALID_ACTIONS:
            if valid.lower() == action_filter.strip().lower():
                normalized_action = valid
                break
        if normalized_action not in _VALID_ACTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"action_filter must be one of {sorted(_VALID_ACTIONS)}",
            )

    items, total = repo.read_comparison(
        tenant_id, source_vpl_id, target_vpl_id,
        changed_only, normalized_action, search, page, page_size,
    )

    return {
        "source_vpl_id": source_vpl_id,
        "target_vpl_id": target_vpl_id,
        "cycle_id": source["cycle_id"],
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
