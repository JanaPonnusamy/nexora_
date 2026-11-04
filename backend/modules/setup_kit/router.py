"""Nexora Setup endpoints (signed-in user; super admin picks the store).

  GET  /api/setup/v1/stores                      stores this login may bind the PC to
  POST /api/setup/v1/plan                        components + package per this PC's spec
  GET  /api/setup/v1/packages/controller/{ver}   Device Controller download for the kit
  POST /api/setup/v1/install                     queue signed `install` commands
  GET  /api/setup/v1/commands?ids=a,b            their progress
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from dependencies.auth import get_current_user
from modules.setup_kit import service

router = APIRouter(prefix="/api/setup/v1", tags=["Nexora Setup"])


class PlanRequest(BaseModel):
    spec: dict = Field(default_factory=dict)


class InstallRequest(BaseModel):
    controller_device_id: str = Field(..., min_length=1, max_length=60)
    components: list[str] = Field(default_factory=list)
    install_dirs: dict[str, str] = Field(default_factory=dict)


@router.get("/stores")
def stores(user: dict = Depends(get_current_user)):
    return service.bindable_stores(user)


@router.post("/plan")
def plan(body: PlanRequest, user: dict = Depends(get_current_user)):
    return service.plan(body.spec, user)


@router.get("/packages/controller/{version}")
async def controller_package(version: str, _: dict = Depends(get_current_user)):
    # A first download may be fetched from a peer node: keep it off the event loop.
    path, file_name = await run_in_threadpool(service.controller_package, version)
    return FileResponse(path, filename=file_name, media_type="application/octet-stream")


@router.post("/install")
def install(body: InstallRequest, user: dict = Depends(get_current_user)):
    return service.queue_install(body.controller_device_id, body.components,
                                 body.install_dirs, user)


@router.get("/commands")
def commands(ids: str = Query(..., max_length=2000), user: dict = Depends(get_current_user)):
    return service.command_status([i.strip() for i in ids.split(",") if i.strip()][:20], user)
