"""HTTP surface for the Remote Order Agent contract (docs/02_HO_API_Contract.md).

Base: /api/nmv/v1. The whole surface is allow-listed past app.py's JWT
require_auth middleware (the device presents an OPAQUE token, not a JWT), so
authentication lives entirely in ``authenticate_device`` below: token lookup +
store-header match + HMAC-SHA256 request-signature verification. ``agent/register``
is the one intentionally-unauthenticated route (the one-time code authorises it).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from modules.remote_order_agent import repository, security, service
from modules.remote_order_agent.exceptions import AgentContractError
from modules.remote_order_agent.schemas import (
    HeartbeatRequest,
    OrderAckRequest,
    OrderResultsRequest,
    RegisterRequest,
)

router = APIRouter(prefix="/api/nmv/v1", tags=["Remote Order Agent"])


def _guard(store, fn):
    """Run fn, turning an AgentContractError into the agent's error envelope +
    the documented HTTP status (the agent reads error.retryable to decide)."""
    try:
        return fn()
    except AgentContractError as exc:
        return JSONResponse(
            status_code=exc.http_status,
            content=security.error_envelope(store, exc.code, exc.message, exc.retryable),
        )


async def authenticate_device(request: Request) -> dict:
    """Authenticate a signed agent request: opaque bearer token -> device row,
    store-header match, then HMAC signature over (ts, METHOD, path+query, body)."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = auth[7:].strip()

    repository.ensure_device_schema()
    device = repository.get_device_by_token_hash(security.hash_token(token))
    if not device:
        raise HTTPException(status_code=401, detail="unknown device token")
    if device.get("status") != "active":
        raise HTTPException(status_code=403, detail="device is revoked")

    hdr_store_id = (request.headers.get("x-nexora-store-id") or "").strip()
    hdr_store_code = (request.headers.get("x-nexora-store-code") or "").strip()
    if hdr_store_id and hdr_store_id.lower() != device["store_id"].lower():
        raise HTTPException(status_code=403, detail="store id mismatch")
    if hdr_store_code and hdr_store_code != device["store_code"]:
        raise HTTPException(status_code=403, detail="store code mismatch")

    ts = request.headers.get("x-nexora-timestamp", "")
    sig = request.headers.get("x-nexora-signature", "")
    body = await request.body()
    path_and_query = request.url.path + (("?" + request.url.query) if request.url.query else "")
    ok, reason = security.verify_signature(
        device["device_id"], ts, request.method, path_and_query, body, sig
    )
    if not ok:
        raise HTTPException(status_code=401, detail="signature: " + reason)

    try:
        store = service.resolve_store(device["store_code"])
    except AgentContractError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.message)
    return {"device": device, "store": store}


# ---- routes ---------------------------------------------------------------

@router.post("/agent/register")
def agent_register(body: RegisterRequest):
    return _guard(None, lambda: service.register(body))


@router.post("/agent/heartbeat")
def agent_heartbeat(body: HeartbeatRequest, ctx: dict = Depends(authenticate_device)):
    return _guard(ctx["store"], lambda: service.heartbeat(ctx["store"], ctx["device"], body))


@router.get("/orders/pending")
def orders_pending(limit: int = Query(5, ge=1, le=50), ctx: dict = Depends(authenticate_device)):
    return _guard(ctx["store"], lambda: service.orders_pending(ctx["store"], limit))


@router.post("/orders/{order_id}/ack")
def orders_ack(order_id: int, body: OrderAckRequest, ctx: dict = Depends(authenticate_device)):
    return _guard(ctx["store"], lambda: service.order_ack(ctx["store"], order_id, body))


@router.post("/order-results")
def order_results(body: OrderResultsRequest, ctx: dict = Depends(authenticate_device)):
    return _guard(ctx["store"], lambda: service.order_results(ctx["store"], ctx["device"], body))
