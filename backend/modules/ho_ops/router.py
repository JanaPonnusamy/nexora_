"""HO backend self-update API (super-admin).

`/api/ho-ops/*` sits under `/api/`, so the app's auth middleware already requires
a Bearer token; each handler additionally requires super-admin. `status` and
`self-update` act on THIS node; `nodes` and `update` orchestrate across the peer
HO nodes in the bootstrap ho_routes registry (server-side, no CORS).
"""
from fastapi import APIRouter, Depends, Header

from dependencies.store_scope import require_super_admin
from modules.ho_ops import service
from modules.ho_ops.schemas import UpdateNodesRequest

router = APIRouter(prefix="/api/ho-ops", tags=["HO Ops"])


@router.get("/status")
def status(_: dict = Depends(require_super_admin)):
    """This node's live git/version status."""
    return service.local_status()


@router.post("/self-update")
def self_update(_: dict = Depends(require_super_admin)):
    """Pull origin/main + reinstall + restart THIS node (detached)."""
    return service.start_self_update()


@router.get("/nodes")
def nodes(_: dict = Depends(require_super_admin),
          authorization: str | None = Header(default=None)):
    """This node + every peer HO node's status."""
    return service.list_nodes(authorization)


@router.post("/update")
def update(payload: UpdateNodesRequest,
           _: dict = Depends(require_super_admin),
           authorization: str | None = Header(default=None)):
    """Trigger self-update on the chosen nodes (peers over HTTP, self direct)."""
    return service.update_nodes([t.model_dump() for t in payload.targets],
                                authorization)
