"""HO backend self-update API (super-admin).

`/api/ho-ops/*` sits under `/api/`, so the app's auth middleware already requires
a Bearer token; each handler additionally requires super-admin. `status` and
`self-update` act on THIS node; `nodes` and `update` orchestrate across the peer
HO nodes in the bootstrap ho_routes registry (server-side, no CORS). The
`backend-release/*` endpoints let exe nodes pull a published bundle from the
build node.
"""
from fastapi import APIRouter, Body, Depends, Header
from fastapi.responses import FileResponse

from dependencies.store_scope import require_super_admin
from modules.ho_ops import service
from modules.ho_ops.schemas import SelfUpdateRequest, UpdateNodesRequest

router = APIRouter(prefix="/api/ho-ops", tags=["HO Ops"])


@router.get("/status")
def status(_: dict = Depends(require_super_admin)):
    """This node's live git/version status."""
    return service.local_status()


@router.post("/self-update")
def self_update(payload: SelfUpdateRequest = Body(default=SelfUpdateRequest()),
                _: dict = Depends(require_super_admin),
                authorization: str | None = Header(default=None)):
    """Update THIS node (git: pull+restart; exe: pull bundle + swap), detached."""
    return service.start_self_update(source_url=payload.source_url,
                                     auth_header=authorization)


@router.get("/nodes")
def nodes(_: dict = Depends(require_super_admin),
          authorization: str | None = Header(default=None)):
    """This node + every peer HO node's status, with the latest published release."""
    return service.list_nodes(authorization)


@router.post("/update")
def update(payload: UpdateNodesRequest,
           _: dict = Depends(require_super_admin),
           authorization: str | None = Header(default=None)):
    """Trigger self-update on the chosen nodes (peers over HTTP, self direct)."""
    return service.update_nodes([t.model_dump() for t in payload.targets],
                                authorization, source_url=payload.source_url)


# ---- published HO backend release (exe nodes pull these) ------------------

@router.get("/backend-release/latest")
def backend_release_latest(_: dict = Depends(require_super_admin)):
    """Manifest of the newest HO backend bundle this node has published."""
    return service.latest_backend_release() or {}


@router.get("/backend-release/download/{version}")
def backend_release_download(version: str, _: dict = Depends(require_super_admin)):
    path, file_name = service.backend_release_path(version)
    return FileResponse(path, filename=file_name, media_type="application/zip")
