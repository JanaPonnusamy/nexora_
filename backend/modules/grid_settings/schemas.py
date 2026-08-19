from typing import Any, Optional

from pydantic import BaseModel


class GridSettingsResponse(BaseModel):
    grid_key: str
    settings: Optional[dict[str, Any]] = None
    updated_at: Optional[str] = None


class GridSettingsSave(BaseModel):
    settings: dict[str, Any]
