from pydantic import BaseModel
from fastapi import APIRouter

from .service import get_settings, save_settings


router = APIRouter(prefix="/api/automation/settings", tags=["Automation Settings"])


class AutomationSettingsPayload(BaseModel):
    repo_path: str
    python_command: str


@router.get("")
def read_automation_settings():
    return get_settings()


@router.put("")
def update_automation_settings(payload: AutomationSettingsPayload):
    return save_settings(payload.repo_path, payload.python_command)
