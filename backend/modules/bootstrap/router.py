"""Public HO discovery endpoint.

GET /api/bootstrap/routes is intentionally unauthenticated: a store agent or
desktop client calls it BEFORE it has any credential, precisely to learn where
HO currently lives. It returns only public routing info (URLs + ordering), no
secrets. Registered as a public path in api/app.py's require_auth middleware.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dependencies.store_scope import require_super_admin
from modules.bootstrap import repository as repo

router = APIRouter(prefix="/api/bootstrap", tags=["Bootstrap / Discovery"])
admin_router = APIRouter(prefix="/api/ho-routes", tags=["HO Route Maintenance"])


@router.get("/routes")
def get_routes():
    routes = repo.get_active_routes()
    return {
        "routes": routes,
        # Convenience: the ordered URL list on its own, so a client can just do
        # `for url in resp["urls"]: try url` without re-sorting.
        "urls": [r["url"] for r in routes],
    }


# ---- maintenance UI (super-admin): manage the HO route list ---------------
#
# Adding the NEW HO's URL here while the CURRENT HO is up is how a planned HO
# migration works: every agent/client pulls this list each cycle and caches it,
# so they learn the new route BEFORE the old HO dies and fail over to it
# automatically when it does. (NB: this only pushes the URL - the new HO must
# already hold the platform data: dbo.stores, device_registrations,
# device_store_assignments, sync.*.)

class RouteIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=50)
    url: str = Field(..., min_length=1, max_length=500)
    route_order: int = 100
    is_active: bool = True


class RoutePatch(BaseModel):
    label: str | None = Field(None, max_length=50)
    url: str | None = Field(None, max_length=500)
    route_order: int | None = None
    is_active: bool | None = None


@admin_router.get("")
def list_routes(_: dict = Depends(require_super_admin)):
    return {"routes": repo.list_all_routes()}


@admin_router.post("")
def create_route(body: RouteIn, _: dict = Depends(require_super_admin)):
    route_id = repo.add_route(body.label, body.url, body.route_order, body.is_active)
    return {"route_id": route_id, "routes": repo.list_all_routes()}


@admin_router.put("/{route_id}")
def edit_route(route_id: int, body: RoutePatch, _: dict = Depends(require_super_admin)):
    affected = repo.update_route(
        route_id, body.label, body.url, body.route_order, body.is_active
    )
    if not affected:
        raise HTTPException(status_code=404, detail="Route not found")
    return {"routes": repo.list_all_routes()}


@admin_router.delete("/{route_id}")
def remove_route(route_id: int, _: dict = Depends(require_super_admin)):
    repo.delete_route(route_id)
    return {"routes": repo.list_all_routes()}
