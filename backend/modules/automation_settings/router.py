from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from dependencies.auth import get_current_user
from dependencies.store_scope import has_unrestricted_scope
from .service import get_settings, save_settings


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if not has_unrestricted_scope(current_user):
        raise HTTPException(status_code=403, detail="Automation Settings is restricted to platform admins.")
    return current_user


router = APIRouter(prefix="/api/automation/settings", tags=["Automation Settings"], dependencies=[Depends(require_admin)])


class AutomationSettingsPayload(BaseModel):
    repo_path: str
    python_command: str


@router.get("")
def read_automation_settings():
    return get_settings()


@router.put("")
def update_automation_settings(payload: AutomationSettingsPayload):
    return save_settings(payload.repo_path, payload.python_command)
