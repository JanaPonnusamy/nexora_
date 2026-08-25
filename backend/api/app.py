import mimetypes
import os
import re

import jwt
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.database import get_connection
from config.security import decode_access_token, decode_setup_token

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
from modules.agent_ops.router import (
    router as agent_ops_router,
    agent_router as agent_ops_agent_router,
)
from modules.stock_availability.router import (
    router as stock_availability_router
)
from modules.stock_check_report.router import (
    router as stock_check_report_router
)
from modules.label_exporter.router import (
    router as label_exporter_router
)
from modules.nmw_sales_report.router import (
    router as nmw_sales_report_router
)
from modules.stock_integrity.router import (
    router as stock_integrity_router
)
from modules.supplier_stock_analysis.router import (
    router as supplier_stock_analysis_router
)
from modules.procurement.router import (
    router as procurement_router
)
from modules.reports.router import (
    router as reports_router
)
from modules.expiry_report.router import (
    router as expiry_report_router
)
from modules.expiry_stock.router import (
    router as expiry_stock_router
)
from modules.time_report.router import (
    router as time_report_router
)
from modules.product_mapping.router import (
    router as product_mapping_router
)
from modules.document_extraction.router import (
    router as document_extraction_router
)
from modules.pass_gen.router import (
    router as pass_gen_router
)
from modules.legacy_order.router import (
    router as legacy_order_router
)
from modules.grid_settings.router import (
    router as grid_settings_router
)
from modules.desktop_client.router import (
    router as desktop_client_router
)
from modules.automation_settings.router import (
    router as automation_settings_router
)
from modules.whatsapp.router import (
    router as whatsapp_router
)
from modules.audit.router import router as audit_router
from modules.audit.middleware import AuditFailureMiddleware
from modules.audit.repository import ensure_schema as ensure_audit_schema
from modules.mobile_bff.router import router as mobile_bff_router
from modules.mobile_bff.repository import ensure_schema as ensure_mobile_bff_schema

try:
    ensure_audit_schema()
except Exception:
    pass

try:
    ensure_mobile_bff_schema()
except Exception:
    pass

app = FastAPI(title='NEXORA API')

# Allowed CORS origins are configurable for production (UNINEX_CORS_ORIGINS,
# comma separated) so the SPA can be reached over several routes at once — a
# local LAN IP, a public domain (tunnel), a static IP, etc. The dev defaults are
# kept when the variable is unset. When the SPA is served from this same service
# (UNINEX_FRONTEND_DIR) requests are same-origin and CORS is not exercised at all.
#
# For a whole subnet (any LAN host) set a pattern instead, e.g.
#   UNINEX_CORS_ORIGIN_REGEX=http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+)(:\d+)?
# "null" is always included: a packaged Electron app (e.g. supplier-stock-client)
# loads its UI via file://, and Chromium sends "Origin: null" on every fetch from
# a file:// page. Auth is still enforced per-request via JWT bearer token
# regardless of origin, so allowing it here only affects which origins the
# browser lets read the response.
_cors_env = os.getenv('UNINEX_CORS_ORIGINS')
_allowed_origins = (
    [o.strip() for o in _cors_env.split(',') if o.strip()] + ['null']
    if _cors_env else
    ['http://localhost:5173', 'http://127.0.0.1:5173', 'null']
)
_cors_regex = os.getenv('UNINEX_CORS_ORIGIN_REGEX') or r'http://(localhost|127\.0\.0\.1)(:\d+)?'
_cors_regex_compiled = re.compile(_cors_regex)

# Every /api/* route requires a valid JWT except /api/auth/login itself.
# Previously nothing enforced auth at all past the login screen - any client
# that could reach the port could call every endpoint. This is the gate that
# has to exist before the API is reachable from outside the LAN.
_PUBLIC_API_PATHS = {
    '/api/auth/login',
    '/api/auth/setup-login',
    # Mobile BFF. /handshake must answer before a client has any credential, and
    # /auth/refresh authenticates with the refresh token in its body precisely
    # because the bearer token has expired by the time it is called.
    '/api/mobile/v1/handshake',
    '/api/mobile/v1/auth/login',
    '/api/mobile/v1/auth/refresh',
}

# Read-only provisioning lookups used by the store-agent setup/settings tool,
# which runs unattended on store PCs with no user session to hold a JWT.
# Scoped to GET only and to these exact patterns so tenant/store CRUD
# (POST/PUT/PATCH on the same routers) stays behind auth.
_SETUP_READ_PATTERNS = (
    re.compile(r'^/api/tenants$'),
    re.compile(r'^/api/stores$'),
    re.compile(r'^/api/stores/tenant/[^/]+$'),
    re.compile(r'^/api/stores/[^/]+/agent-config$'),
)

def _is_setup_read(request: Request) -> bool:
    return request.method == 'GET' and any(
        p.match(request.url.path) for p in _SETUP_READ_PATTERNS
    )

# The store-agent sync protocol (unattended service on each store PC - no
# user, no JWT) predates this auth gate and still talks to these /api/sync
# and /api/desktop-client paths (only /tasks/poll, /register and /heartbeat
# were ever moved under the already-exempt /agent/* prefix). Without this
# exemption every store agent's task polling, chunk upload and first-contact
# device activation started failing with 401 the moment the gate went in -
# sync silently stopped making progress on every pending task, network-wide.
_PUBLIC_AGENT_PATTERNS = (
    re.compile(r'^/api/sync/tasks/pending/[^/]+$'),
    re.compile(r'^/api/sync/tasks/[^/]+/(start|complete|fail)$'),
    re.compile(r'^/api/sync/configuration/[^/]+$'),
    re.compile(r'^/api/sync/schema/register$'),
    re.compile(r'^/api/sync/chunks/(upload|ack)$'),
    re.compile(r'^/api/sync/chunks/status/[^/]+$'),
    re.compile(r'^/api/sync/tables/report$'),
    re.compile(r'^/api/desktop-client/activate/request$'),
    # A fresh, un-activated PC has no user session: it polls /config (by its own
    # client_id) to learn when HO has approved it and which store it was bound
    # to, and /heartbeat to report liveness. Both are keyed by an opaque
    # client_id UUID and return only that device's own binding.
    re.compile(r'^/api/desktop-client/config$'),
    re.compile(r'^/api/desktop-client/heartbeat$'),
    re.compile(r'^/api/stores/[^/]+/agent-config$'),
)

def _is_public_agent_call(request: Request) -> bool:
    return any(p.match(request.url.path) for p in _PUBLIC_AGENT_PATTERNS)

def _with_cors(response, request: Request):
    # require_auth's early returns bypass CORSMiddleware (regardless of
    # registration order they can end up wrapping outside it), so a rejected
    # request would reach the browser with no Access-Control-Allow-Origin
    # header - which browsers report as a misleading CORS error instead of
    # surfacing the real 401. Stamp the same headers CORSMiddleware would.
    origin = request.headers.get('origin')
    if origin and (origin in _allowed_origins or _cors_regex_compiled.fullmatch(origin)):
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Vary'] = 'Origin'
    return response

@app.middleware('http')
async def require_auth(request: Request, call_next):
    path = request.url.path
    if (request.method != 'OPTIONS' and path.startswith('/api/')
            and path not in _PUBLIC_API_PATHS
            and not _is_public_agent_call(request)):
        setup_token = request.headers.get('x-nexora-setup-token', '').strip()
        if setup_token:
            try:
                claims = decode_setup_token(setup_token)
            except jwt.ExpiredSignatureError:
                return _with_cors(JSONResponse(status_code=401, content={'detail': 'Setup token expired'}), request)
            except jwt.InvalidTokenError:
                return _with_cors(JSONResponse(status_code=401, content={'detail': 'Invalid setup token'}), request)
            if claims.get('scope') != 'setup_readonly' or not _is_setup_read(request):
                return _with_cors(JSONResponse(status_code=403, content={'detail': 'Setup token is not allowed for this endpoint'}), request)
        else:
            header = request.headers.get('authorization', '')
            if not header.lower().startswith('bearer '):
                return _with_cors(JSONResponse(status_code=401, content={'detail': 'Not authenticated'}), request)
            token = header[7:].strip()
            try:
                decode_access_token(token)
            except jwt.ExpiredSignatureError:
                return _with_cors(JSONResponse(status_code=401, content={'detail': 'Token expired'}), request)
            except jwt.InvalidTokenError:
                return _with_cors(JSONResponse(status_code=401, content={'detail': 'Invalid token'}), request)
    return await call_next(request)

# AuditFailureMiddleware captures unhandled exceptions and HTTP 4xx/5xx failures
# (including 401/403 authorization denials) on audited endpoints.
app.add_middleware(AuditFailureMiddleware)

# Added after require_auth so it wraps as the OUTERMOST middleware (Starlette
# builds the stack in reverse registration order) - otherwise require_auth's
# early 401 returns bypass this middleware entirely and reach the browser
# without CORS headers, which shows up as a misleading CORS error instead
# of the real 401.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=_cors_regex,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(auth_router)
app.include_router(audit_router)
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
app.include_router(stock_check_report_router)
app.include_router(label_exporter_router)
app.include_router(nmw_sales_report_router)
app.include_router(stock_integrity_router)
app.include_router(supplier_stock_analysis_router)
app.include_router(procurement_router)
app.include_router(reports_router)
app.include_router(expiry_report_router)
app.include_router(expiry_stock_router)
app.include_router(time_report_router)
app.include_router(product_mapping_router)
app.include_router(document_extraction_router)
app.include_router(pass_gen_router)
app.include_router(legacy_order_router)
app.include_router(desktop_client_router)
app.include_router(automation_settings_router)
app.include_router(grid_settings_router)
app.include_router(whatsapp_router)
app.include_router(agent_ops_router)
app.include_router(agent_ops_agent_router)
app.include_router(mobile_bff_router)

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

# Desktop client auto-update feed (electron-updater "generic" provider). Serves
# latest.yml + the packaged installer from UNINEX_UPDATES_DIR (default
# backend/updates) so store clients pull new versions straight from HO. Mounted
# before the SPA catch-all below so /updates/* is never swallowed by it.
from fastapi.staticfiles import StaticFiles as _UpdatesStaticFiles

_updates_dir = os.getenv(
    'UNINEX_UPDATES_DIR',
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'updates'),
)
os.makedirs(_updates_dir, exist_ok=True)
app.mount('/updates', _UpdatesStaticFiles(directory=_updates_dir), name='desktop-updates')


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
