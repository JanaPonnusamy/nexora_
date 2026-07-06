"""Service layer for the Procurement module — Cycle.

Thin orchestration over the repository: validation, tenant enforcement and
shaping. No business intelligence (calculation, supplier, stock, pending,
shortage, expiry) — those arrive in later sprints. The Workspace concept has
been removed from the approved model.
"""

from fastapi import HTTPException

from modules.procurement import repository


# --------------------------------------------------------------------------
# Procurement Cycle
# --------------------------------------------------------------------------

def create_cycle(payload):
    return repository.create_cycle(payload)


def get_cycle(tenant_id, cycle_id):
    cycle = repository.get_cycle(tenant_id, cycle_id)
    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return cycle


def list_cycles(tenant_id, status, search, page, page_size, store_id=None):
    items, total = repository.list_cycles(
        tenant_id, status, search, page, page_size, store_id
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def update_cycle(tenant_id, cycle_id, payload):
    updated = repository.update_cycle(tenant_id, cycle_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return updated


def delete_cycle(tenant_id, cycle_id, deleted_by):
    if not repository.delete_cycle(tenant_id, cycle_id, deleted_by):
        raise HTTPException(status_code=404, detail="Cycle not found")
    return {"status": "deleted", "cycle_id": cycle_id}
