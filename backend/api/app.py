import mimetypes
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.database import get_connection

# Force correct static MIME types at startup. StaticFiles resolves Content-Type
# via mimetypes.guess_type, which on Windows reads the registry where .js is
# frequently mapped to text/plain - causing Chrome to refuse Vite's ES modules.
# add_type() overrides those mappings so served assets get the right type.
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('application/javascript', '.mjs')
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('image/svg+xml', '.svg')
mimetypes.add_type('font/woff', '.woff')
mimetypes.add_type('font/woff2', '.woff2')

from controllers.auth_controller import router as auth_router
from controllers.tenant_controller import router as tenant_router
from controllers.store_controller import router as store_router
from controllers.role_controller import router as role_router
from controllers.user_role_controller import router as user_role_router
from controllers.module_controller import router as module_router
from controllers.role_module_access_controller import router as role_module_access_router
from controllers.user_controller import router as user_router, relations_router as user_relations_router
from controllers.permission_controller import router as permission_router
from controllers.sync_admin_controller import router as sync_admin_router
from modules.sync.router import router as sync_router
from modules.sync.table_registry_router import (
    router as table_registry_router
)
from modules.sync.table_master_router import (
    router as table_master_router
)

from modules.sync.catalog_router import (
    router as catalog_router
)
from modules.store_agent.config_router import (
    router as store_agent_config_router
)
from modules.sync.runtime_router import (
    router as sync_runtime_router,
    agent_router as sync_agent_router,
)
from modules.sync.shared_table_builder_router import (
    router as sync_shared_table_router,
)
from modules.stock_availability.router import (
    router as stock_availability_router
)
from modules.procurement.router import (
    router as procurement_router
)
from modules.reports.router import (
    router as reports_router
)
from modules.product_mapping.router import (
    router as product_mapping_router
)
from modules.document_extraction.router import (
    router as document_extraction_router
)

app = FastAPI(title='NEXORA API')

# Allowed CORS origins are configurable for production (UNINEX_CORS_ORIGINS,
# comma separated) so the SPA can be reached over several routes at once — a
# local LAN IP, a public domain (tunnel), a static IP, etc. The dev defaults are
# kept when the variable is unset. When the SPA is served from this same service
# (UNINEX_FRONTEND_DIR) requests are same-origin and CORS is not exercised at all.
#
# For a whole subnet (any LAN host) set a pattern instead, e.g.
#   UNINEX_CORS_ORIGIN_REGEX=http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?
_cors_env = os.getenv('UNINEX_CORS_ORIGINS')
_allowed_origins = (
    [o.strip() for o in _cors_env.split(',') if o.strip()]
    if _cors_env else
    ['http://localhost:5173', 'http://127.0.0.1:5173']
)
_cors_regex = os.getenv('UNINEX_CORS_ORIGIN_REGEX') or None

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)
app.include_router(tenant_router)
app.include_router(store_router)
app.include_router(role_router)
app.include_router(user_role_router)
app.include_router(module_router)
app.include_router(role_module_access_router)
app.include_router(user_router)
app.include_router(user_relations_router)
app.include_router(permission_router)
app.include_router(sync_admin_router)
app.include_router(sync_router)
app.include_router(table_registry_router)
app.include_router(catalog_router)
app.include_router(table_master_router)
app.include_router(store_agent_config_router)
app.include_router(sync_runtime_router)
app.include_router(sync_agent_router)
app.include_router(sync_shared_table_router)
app.include_router(stock_availability_router)
app.include_router(procurement_router)
app.include_router(reports_router)
app.include_router(product_mapping_router)
app.include_router(document_extraction_router)

@app.get('/health')
def health():
    return {'status':'healthy'}

@app.get('/health/db')
def health_db():
    try:
        conn = get_connection()
        conn.close()
        return {'status':'healthy','database':'connected'}
    except Exception as ex:
        return {'status':'failed','error':str(ex)}

# Optional single-origin production serving: when the HO installer sets
# UNINEX_FRONTEND_DIR, this same service also serves the SPA build and a
# generated /config.js that points the SPA at the configured API URL. API
# routers above are registered first and therefore take precedence over the
# routes below. Unset in development, so nothing changes when running locally.
_frontend_dir = os.getenv('UNINEX_FRONTEND_DIR')
if _frontend_dir and os.path.isdir(_frontend_dir):
    from fastapi.responses import FileResponse, Response
    from fastapi.staticfiles import StaticFiles

    # Empty (the default) = same-origin/relative: the SPA calls whichever host
    # served it, so LAN IP + domain + static IP all work from one deployment.
    # Set UNINEX_API_URL only for a cross-origin deploy (SPA and API on different
    # hosts), in which case it must be an absolute URL.
    _api_base = os.getenv('UNINEX_API_URL', '')

    @app.get('/config.js')
    def runtime_config():
        body = f'window.__UNINEX_API_BASE__ = "{_api_base}";\n'
        return Response(content=body, media_type='application/javascript')

    # Vite's hashed JS/CSS bundles live under /assets — served directly (with
    # correct caching/range support) via StaticFiles.
    _assets_dir = os.path.join(_frontend_dir, 'assets')
    if os.path.isdir(_assets_dir):
        app.mount('/assets', StaticFiles(directory=_assets_dir), name='frontend-assets')

    # Catch-all SPA fallback — MUST be the last route registered so every API
    # router above still wins on its own path. A bare StaticFiles mount at "/"
    # only serves an existing file or a directory's index.html; it does not
    # know about React Router's client-side routes (e.g. /procurement/
    # intelligence), so a direct navigation or hard refresh on one of those
    # 404s at the HTTP layer even though the route exists in the SPA. This
    # handler serves the matching file when one exists on disk (favicon,
    # manifest, etc.) and otherwise falls back to index.html so React Router
    # can resolve the path client-side.
    @app.get('/{full_path:path}')
    def spa_fallback(full_path: str):
        candidate = os.path.join(_frontend_dir, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_frontend_dir, 'index.html'))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
