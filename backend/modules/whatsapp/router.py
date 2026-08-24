from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from dependencies.store_scope import require_super_admin
from .service import (
    check_status,
    delete_profile,
    delete_target,
    get_login_qr,
    get_state,
    launch_qr,
    logout_profile,
    send_message,
    send_target_message,
    sync_target_messages,
    update_settings,
    upsert_profile,
    upsert_target,
)


router = APIRouter(prefix="/api/whatsapp", tags=["WhatsApp"])


class WhatsAppSettingsPayload(BaseModel):
    browser_command: str = ""
    delivery_mode: str = "manual_browser"
    launch_wait_seconds: int = 15
    headless: bool = True
    manual_fallback: bool = False


class WhatsAppProfilePayload(BaseModel):
    profile_id: str | None = None
    profile_name: str
    owner_type: str = "store"
    owner_name: str = ""
    tenant_id: str = ""
    store_id: str = ""
    default_phone: str = ""
    notes: str = ""
    is_default: bool = False


class WhatsAppTextPayload(BaseModel):
    profile_id: str
    phone: str = ""
    message: str = ""


class WhatsAppTargetPayload(BaseModel):
    target_id: str | None = None
    profile_id: str
    target_kind: str = "contact"
    target_name: str
    target_ref: str
    can_send: bool = True
    can_read: bool = False
    is_active: bool = True
    notes: str = ""


class WhatsAppTargetSendPayload(BaseModel):
    target_id: str
    message: str = ""


@router.get("/state")
def read_whatsapp_state():
    return get_state()


@router.put("/settings")
def save_whatsapp_settings(payload: WhatsAppSettingsPayload, _: dict = Depends(require_super_admin)):
    return update_settings(
        payload.browser_command,
        payload.delivery_mode,
        payload.launch_wait_seconds,
        payload.headless,
        payload.manual_fallback,
    )


@router.post("/profiles")
def save_whatsapp_profile(payload: WhatsAppProfilePayload, _: dict = Depends(require_super_admin)):
    return upsert_profile(payload.model_dump())


@router.delete("/profiles/{profile_id}")
def remove_whatsapp_profile(profile_id: str, _: dict = Depends(require_super_admin)):
    return delete_profile(profile_id)


@router.post("/profiles/{profile_id}/launch")
def launch_whatsapp_qr(profile_id: str, _: dict = Depends(require_super_admin)):
    return launch_qr(profile_id)


@router.get("/profiles/{profile_id}/status")
def read_whatsapp_profile_status(profile_id: str, _: dict = Depends(require_super_admin)):
    return check_status(profile_id)


@router.get("/profiles/{profile_id}/qr")
def read_whatsapp_login_qr(profile_id: str, _: dict = Depends(require_super_admin)):
    return get_login_qr(profile_id)


@router.post("/profiles/{profile_id}/logout")
def logout_whatsapp_profile(profile_id: str, _: dict = Depends(require_super_admin)):
    return logout_profile(profile_id)


@router.post("/send/text")
def send_whatsapp_text(payload: WhatsAppTextPayload):
    return send_message(payload.profile_id, payload.phone, payload.message)


@router.post("/targets")
def save_whatsapp_target(payload: WhatsAppTargetPayload):
    return upsert_target(payload.model_dump())


@router.delete("/targets/{target_id}")
def remove_whatsapp_target(target_id: str):
    return delete_target(target_id)


@router.post("/targets/send")
def send_whatsapp_target(payload: WhatsAppTargetSendPayload):
    return send_target_message(payload.target_id, payload.message)


@router.post("/targets/{target_id}/sync")
def sync_whatsapp_target(target_id: str, limit: int = 20):
    return sync_target_messages(target_id, limit)


@router.post("/send/file")
async def send_whatsapp_file(
    profile_id: str = Form(...),
    phone: str = Form(""),
    message: str = Form(""),
    file: UploadFile = File(...),
):
    content = await file.read()
    return await run_in_threadpool(send_message, profile_id, phone, message, file.filename, content)


@router.post("/targets/send-file")
async def send_whatsapp_target_file(
    target_id: str = Form(...),
    message: str = Form(""),
    file: UploadFile = File(...),
):
    content = await file.read()
    return await run_in_threadpool(send_target_message, target_id, message, file.filename, content)
