"""NMV integration HTTP surface.

All routes are device-bearer authenticated and hard-scoped to a single store
that the calling device must be assigned to. `store_code` in the path is never
trusted on its own -- it is validated against the token's assigned stores
server-side (see get_nmv_context).

The device bearer is an ordinary access token (same signer as every other JWT),
so app.py's require_auth middleware already gates these routes; get_nmv_context
is the second, device-and-store-specific gate.
"""
from __future__ import annotations

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.security import decode_access_token
from dependencies.store_scope import require_super_admin
from modules.device_identity import repository as device_repo
from modules.nmv_integration import enrollment, repository, schemas, service
from modules.nmv_integration.exceptions import NmvIntegrationError

router = APIRouter(prefix="/api/nmv-integration/v1/stores", tags=["NMV Integration"])
admin_router = APIRouter(prefix="/api/nmv-integration/v1/admin", tags=["NMV Integration"])

_bearer = HTTPBearer(auto_error=False)


def _resolve_active_store(store_code: str) -> dict:
    """Resolve store_code to a provisioned, active platform store (shared by the
    admin-generate and device-enroll paths, which have no device token yet)."""
    store = repository.resolve_platform_store(store_code)
    if not store:
        raise HTTPException(status_code=404, detail="Unknown store")
    if not store.get("is_active", True):
        raise HTTPException(status_code=403, detail="Store is inactive")
    return store


def get_nmv_context(store_code: str, credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """Authenticate the device bearer and authorize it for `store_code`.

    Order of checks is deliberate: a bad token is 401, a non-device/unknown
    device is 403, an unknown store is 404, and a device not assigned to the
    store is 403 -- the client can never widen its scope by changing the path.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        claims = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if claims.get("token_kind") != "device":
        raise HTTPException(status_code=403, detail="Device token required")

    device_id = claims.get("device_id")
    device = device_repo.get_device(device_id)
    if not device or device.get("status") != "active":
        raise HTTPException(status_code=403, detail="Device is not registered or has been revoked")

    store = repository.resolve_platform_store(store_code)
    if not store:
        raise HTTPException(status_code=404, detail="Unknown store")
    if not store.get("is_active", True):
        raise HTTPException(status_code=403, detail="Store is inactive")

    token_store_ids = {str(s) for s in (claims.get("store_ids") or [])}
    if store["store_id"] not in token_store_ids:
        raise HTTPException(status_code=403, detail="Device is not authorized for this store")

    return {"device_id": device_id, "store": store, "claims": claims}


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NmvIntegrationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ---- reads ----------------------------------------------------------------

@router.get("/{store_code}/config", response_model=schemas.ConfigResponse)
def get_config(store_code: str, ctx: dict = Depends(get_nmv_context)):
    return _guard(service.get_config, ctx["store"])


@router.get("/{store_code}/manifest", response_model=schemas.ManifestResponse)
def get_manifest(store_code: str, ctx: dict = Depends(get_nmv_context)):
    return _guard(service.get_manifest, ctx["store"])


@router.get("/{store_code}/changes", response_model=schemas.ChangesResponse)
def get_changes(
    store_code: str,
    entity: str = Query(..., min_length=1, max_length=100),
    cursor: str | None = Query(None),
    limit: int = Query(service.MAX_ROWS_PER_PAGE, ge=1, le=service.MAX_ROWS_PER_PAGE),
    ctx: dict = Depends(get_nmv_context),
):
    return _guard(service.get_changes, ctx["store"], entity, cursor, limit)


@router.get("/{store_code}/orders", response_model=schemas.OrdersResponse)
def get_orders(
    store_code: str,
    order_id: int | None = Query(None),
    ctx: dict = Depends(get_nmv_context),
):
    return _guard(service.get_orders, ctx["store"], order_id)


@router.get("/{store_code}/status", response_model=schemas.StatusResponse)
def get_status(store_code: str, ctx: dict = Depends(get_nmv_context)):
    return _guard(service.get_status, ctx["store"])


# ---- writes ---------------------------------------------------------------

@router.post("/{store_code}/uplink", response_model=schemas.UplinkResponse)
def post_uplink(store_code: str, body: schemas.UplinkRequest, ctx: dict = Depends(get_nmv_context)):
    return _guard(service.ingest_uplink, ctx["store"], ctx["device_id"], body)


@router.post("/{store_code}/order-results", response_model=schemas.OrderResultsResponse)
def post_order_results(
    store_code: str, body: schemas.OrderResultsRequest, ctx: dict = Depends(get_nmv_context)
):
    return _guard(service.ingest_order_results, ctx["store"], ctx["device_id"], body)


@router.post("/{store_code}/ack", response_model=schemas.AckResponse)
def post_ack(store_code: str, body: schemas.AckRequest, ctx: dict = Depends(get_nmv_context)):
    return _guard(service.ack, ctx["store"], body.entity, body.watermark)


# ---- enrollment -----------------------------------------------------------
#
# The device-facing enroll endpoint has NO bearer dependency: the device has no
# token yet -- that is the whole point. It authenticates with the one-time code
# in the body, which the repository verifies against the store-bound hash. The
# path is allow-listed in app.py's require_auth middleware (like the signature
# /api/auth/device/token endpoint it complements).

@router.post("/{store_code}/enroll", response_model=schemas.EnrollResponse)
def enroll(store_code: str, body: schemas.EnrollRequest):
    store = _resolve_active_store(store_code)
    return _guard(enrollment.enroll_device, store, body)


# Admin code generation lives under /admin (super-admin bearer required); it is
# NOT allow-listed, so the require_auth middleware + require_super_admin gate it.

@admin_router.post(
    "/stores/{store_code}/enrollment", response_model=schemas.GenerateEnrollmentResponse
)
def generate_enrollment(
    store_code: str,
    body: schemas.GenerateEnrollmentRequest | None = None,
    user: dict = Depends(require_super_admin),
):
    store = _resolve_active_store(store_code)
    ttl = body.ttl_seconds if body else None
    return _guard(enrollment.generate_enrollment_code, store, user, ttl)
