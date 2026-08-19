"""Generic per-user grid display settings — column order/width/padding for
ANY grid in the app, keyed by an arbitrary grid_key string chosen by the
caller. One table (dbo.user_grid_settings), no per-grid backend work needed
for future grids."""

from fastapi import APIRouter, Depends

from dependencies.auth import get_current_user
from modules.grid_settings import service
from modules.grid_settings.schemas import GridSettingsResponse, GridSettingsSave

router = APIRouter(prefix="/api/grid-settings", tags=["Grid Settings"])


@router.get("/{grid_key}", response_model=GridSettingsResponse)
def get_settings(grid_key: str, current_user: dict = Depends(get_current_user)):
    return service.get_settings(current_user["sub"], grid_key)


@router.put("/{grid_key}", response_model=GridSettingsResponse)
def save_settings(grid_key: str, payload: GridSettingsSave, current_user: dict = Depends(get_current_user)):
    return service.save_settings(current_user["sub"], current_user.get("tenant_id"), grid_key, payload.settings)


@router.delete("/{grid_key}")
def reset_settings(grid_key: str, current_user: dict = Depends(get_current_user)):
    service.reset_settings(current_user["sub"], grid_key)
    return {"ok": True}
