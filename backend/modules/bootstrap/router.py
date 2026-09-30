"""Public HO discovery endpoint.

GET /api/bootstrap/routes is intentionally unauthenticated: a store agent or
desktop client calls it BEFORE it has any credential, precisely to learn where
HO currently lives. It returns only public routing info (URLs + ordering), no
secrets. Registered as a public path in api/app.py's require_auth middleware.
"""

from fastapi import APIRouter

from modules.bootstrap import repository as repo

router = APIRouter(prefix="/api/bootstrap", tags=["Bootstrap / Discovery"])


@router.get("/routes")
def get_routes():
    routes = repo.get_active_routes()
    return {
        "routes": routes,
        # Convenience: the ordered URL list on its own, so a client can just do
        # `for url in resp["urls"]: try url` without re-sorting.
        "urls": [r["url"] for r in routes],
    }
