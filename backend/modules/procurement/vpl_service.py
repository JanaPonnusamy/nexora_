"""Service layer for the Virtual Product List (VPL) — Sprint 2.

Business orchestration only: tenant isolation, referential validation, VPL
status lifecycle and duplicate prevention. No procurement calculations, stock
logic or supplier logic.
"""

from fastapi import HTTPException

from modules.procurement import repository as proc_repo
from modules.procurement import vpl_repository as repo


def _require_vpl(tenant_id, vpl_id):
    vpl = repo.get_vpl(tenant_id, vpl_id)
    if not vpl:
        raise HTTPException(status_code=404, detail="VPL not found")
    return vpl


# --------------------------------------------------------------------------
# VPL header
# --------------------------------------------------------------------------

def create_vpl(payload):
    tenant_id = payload["tenant_id"]
    cycle_id = payload["cycle_id"]

    if not proc_repo.cycle_exists(tenant_id, cycle_id):
        raise HTTPException(
            status_code=400,
            detail="cycle_id does not exist for this tenant",
        )
    return repo.create_vpl(payload)


def get_vpl(tenant_id, vpl_id):
    return _require_vpl(tenant_id, vpl_id)


def list_vpls(tenant_id, cycle_id, store_id,
              status, search, page, page_size):
    items, total = repo.list_vpls(
        tenant_id, cycle_id, store_id,
        status, search, page, page_size,
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def refresh_vpl(tenant_id, vpl_id, updated_by):
    """Metadata refresh: re-stamp products and return the VPL to Ready.

    Archived snapshots are immutable. This only advances the snapshot version
    and status lifecycle — it does not compute or fetch business data.
    """
    vpl = _require_vpl(tenant_id, vpl_id)
    if vpl["snapshot_status"] == "Archived":
        raise HTTPException(
            status_code=409, detail="Archived VPL cannot be refreshed"
        )
    repo.set_status(tenant_id, vpl_id, "Refreshing", updated_by)
    repo.bump_products_version(tenant_id, vpl_id)
    repo.set_status(tenant_id, vpl_id, "Ready", updated_by)
    return _require_vpl(tenant_id, vpl_id)


def archive_vpl(tenant_id, vpl_id, updated_by):
    vpl = _require_vpl(tenant_id, vpl_id)
    if vpl["snapshot_status"] == "Archived":
        raise HTTPException(
            status_code=409, detail="VPL is already archived"
        )
    repo.set_status(tenant_id, vpl_id, "Archived", updated_by)
    return _require_vpl(tenant_id, vpl_id)


def delete_vpl(tenant_id, vpl_id):
    if not repo.delete_vpl(tenant_id, vpl_id):
        raise HTTPException(status_code=404, detail="VPL not found")
    return {"status": "deleted", "refresh_id": vpl_id}


# --------------------------------------------------------------------------
# VPL products
# --------------------------------------------------------------------------

def add_product(tenant_id, vpl_id, payload):
    vpl = _require_vpl(tenant_id, vpl_id)
    if vpl["snapshot_status"] == "Archived":
        raise HTTPException(
            status_code=409,
            detail="Cannot add products to an archived VPL",
        )
    if repo.product_in_vpl(tenant_id, vpl_id, payload["product_id"]):
        raise HTTPException(
            status_code=409,
            detail="Product already exists in this VPL",
        )
    return repo.add_product(tenant_id, vpl, payload)


def list_products(tenant_id, vpl_id, search, page, page_size):
    _require_vpl(tenant_id, vpl_id)
    items, total = repo.list_products(tenant_id, vpl_id, search, page, page_size)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def remove_product(tenant_id, vpl_id, product_row_id):
    vpl = _require_vpl(tenant_id, vpl_id)
    if vpl["snapshot_status"] == "Archived":
        raise HTTPException(
            status_code=409,
            detail="Cannot remove products from an archived VPL",
        )
    if not repo.remove_product(tenant_id, vpl_id, product_row_id):
        raise HTTPException(status_code=404, detail="Product not found in VPL")
    return {"status": "removed", "virtual_product_id": product_row_id}
