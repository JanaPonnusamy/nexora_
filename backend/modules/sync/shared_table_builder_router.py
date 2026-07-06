from fastapi import APIRouter

from modules.sync import shared_table_builder_service

router = APIRouter(prefix="/api/sync/shared-tables", tags=["Sync Shared Tables"])


@router.post("/build")
def build_shared_tables():
    return shared_table_builder_service.build_shared_tables()
