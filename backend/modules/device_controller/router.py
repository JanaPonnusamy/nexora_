"""Device Controller APIs.

Three routers:
  * ``router`` (/api/device-controller) - HO admin surface, SUPER-ADMIN ONLY:
    fleet list, signed commands, package catalog, enrollment codes and the
    remote terminal (every keystroke and every byte of output is stored).
  * ``agent_router`` (/api/agent/controller) - what NexoraDeviceController
    calls with its device token: heartbeat, long-poll inbox, command results,
    terminal output, package download.
  * ``enroll_router`` (/api/auth/device-controller) - public: a controller
    proves an HO-issued enrollment code once to register its device key.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse

from dependencies.store_scope import require_super_admin
from modules.device_controller import packages, protocol, repository, service
from modules.device_controller.schemas import (
    BulkCommandRequest,
    CommandRequest,
    CommandResultRequest,
    EnrollCodeRequest,
    EnrollRequest,
    HeartbeatRequest,
    TerminalInputRequest,
    TerminalOpenRequest,
    TerminalOutputRequest,
)
from modules.device_identity.router import get_current_device

router = APIRouter(prefix="/api/device-controller", tags=["Device Controller"])
agent_router = APIRouter(prefix="/api/agent/controller", tags=["Device Controller Agent"])
enroll_router = APIRouter(prefix="/api/auth/device-controller", tags=["Device Controller Agent"])
peer_router = APIRouter(prefix="/api/device-controller/peer", tags=["Device Controller Peer"])


def _actor(user: dict) -> str:
    return str(user.get("username") or user.get("sub") or "")


def _device_id(device: dict) -> str:
    return str(device.get("device_id") or "")


# ---- admin: fleet ---------------------------------------------------------

@router.get("/meta")
def meta(_: dict = Depends(require_super_admin)):
    return {"apps": {k: {"label": protocol.APP_LABELS[k], "actions": sorted(v)}
                     for k, v in protocol.APP_ACTIONS.items()},
            "default_pause_minutes": protocol.DEFAULT_PAUSE_MINUTES}


@router.get("/devices")
def list_devices(_: dict = Depends(require_super_admin)):
    return {"devices": repository.list_devices()}


@router.get("/devices/{device_id}")
def get_device(device_id: str, _: dict = Depends(require_super_admin)):
    device = repository.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device["commands"] = repository.list_commands(device_id, limit=50)
    return device


@router.post("/devices/{device_id}/revoke")
def revoke_device(device_id: str, _: dict = Depends(require_super_admin)):
    return {"revoked": repository.revoke_device(device_id)}


@router.post("/devices/{device_id}/commands")
def create_command(device_id: str, payload: CommandRequest,
                   user: dict = Depends(require_super_admin)):
    return service.create_command(device_id, payload.app_key, payload.action,
                                  payload.args, _actor(user))


@router.post("/commands/bulk")
def create_bulk(payload: BulkCommandRequest, user: dict = Depends(require_super_admin)):
    return service.create_bulk(payload.device_ids, payload.app_key, payload.action,
                               payload.args, _actor(user))


@router.get("/commands")
def list_commands(device_id: str | None = None, _: dict = Depends(require_super_admin)):
    return {"commands": repository.list_commands(device_id, limit=200)}


@router.post("/commands/{command_id}/cancel")
def cancel_command(command_id: str, user: dict = Depends(require_super_admin)):
    return service.cancel_command(command_id, _actor(user))


@router.get("/packages")
def list_packages(_: dict = Depends(require_super_admin)):
    return service.list_packages()


# ---- admin: enrollment codes ---------------------------------------------

@router.get("/enroll-codes")
def list_enroll_codes(_: dict = Depends(require_super_admin)):
    return {"codes": repository.list_enroll_codes()}


@router.post("/enroll-codes")
def create_enroll_code(payload: EnrollCodeRequest, user: dict = Depends(require_super_admin)):
    return service.new_enroll_code(payload.note, payload.hours, payload.max_uses, _actor(user))


@router.post("/enroll-codes/{code}/revoke")
def revoke_enroll_code(code: str, _: dict = Depends(require_super_admin)):
    return {"revoked": repository.revoke_enroll_code(code)}


# ---- admin: remote terminal -----------------------------------------------

@router.get("/terminals")
def list_terminals(device_id: str | None = None, active: bool = False,
                   _: dict = Depends(require_super_admin)):
    return service.list_sessions(device_id, active)


@router.post("/terminals")
def open_terminal(payload: TerminalOpenRequest, user: dict = Depends(require_super_admin)):
    return service.open_terminal(payload.device_id, _actor(user))


@router.post("/terminals/{session_id}/input")
def terminal_input(session_id: str, payload: TerminalInputRequest,
                   user: dict = Depends(require_super_admin)):
    return service.send_input(session_id, payload.data, _actor(user))


@router.post("/terminals/{session_id}/reset")
def terminal_reset(session_id: str, user: dict = Depends(require_super_admin)):
    return service.reset_terminal(session_id, _actor(user))


@router.post("/terminals/{session_id}/close")
def terminal_close(session_id: str, user: dict = Depends(require_super_admin)):
    return service.close_terminal(session_id, _actor(user))


@router.get("/terminals/{session_id}/output")
async def terminal_output(session_id: str, after: int = 0, wait: float = 15,
                          _: dict = Depends(require_super_admin)):
    return await service.terminal_output_after(session_id, after, wait)


# ---- device (controller) --------------------------------------------------

@agent_router.post("/heartbeat")
def heartbeat(payload: HeartbeatRequest, request: Request,
              device: dict = Depends(get_current_device)):
    observed_ip = request.client.host if request.client else None
    return service.record_heartbeat(_device_id(device), payload.model_dump(), observed_ip)


@agent_router.get("/poll")
async def poll(wait: float = 20, device: dict = Depends(get_current_device)):
    return await service.poll_messages(_device_id(device), wait)


@agent_router.post("/commands/{command_id}/result")
def command_result(command_id: str, payload: CommandResultRequest,
                   device: dict = Depends(get_current_device)):
    return service.command_result(_device_id(device), command_id, payload.status,
                                  payload.exit_code, payload.result_text)


@agent_router.post("/terminals/{session_id}/output")
def terminal_output_from_device(session_id: str, payload: TerminalOutputRequest,
                                device: dict = Depends(get_current_device)):
    return service.terminal_output(_device_id(device), session_id, payload.chunks,
                                   payload.closed, payload.reason)


@agent_router.get("/packages/{app_key}/{version}")
def download_package(app_key: str, version: str, device: dict = Depends(get_current_device)):
    path, file_name = service.package_file(app_key, version)
    return FileResponse(path, filename=file_name, media_type="application/octet-stream")


@enroll_router.post("/enroll")
def enroll(payload: EnrollRequest):
    return service.enroll_with_code(payload)


# ---- peer mirror (HO node <-> HO node, shared NEXORA_PACKAGE_PEER_KEY) -----

def _require_peer(key: str | None):
    if not packages.peer_key_ok(key):
        raise HTTPException(status_code=403, detail="Peer key required")


@peer_router.get("/catalog")
def peer_catalog(x_nexora_peer_key: str | None = Header(default=None)):
    _require_peer(x_nexora_peer_key)
    return {"packages": packages.local_catalog()}


@peer_router.get("/packages/{app_key}/{version}")
def peer_package(app_key: str, version: str, x_nexora_peer_key: str | None = Header(default=None)):
    _require_peer(x_nexora_peer_key)
    found = packages.local_package_path(app_key, version)
    if not found:
        raise HTTPException(status_code=404, detail="Package not held by this HO node")
    path, file_name = found
    return FileResponse(path, filename=file_name, media_type="application/octet-stream")
