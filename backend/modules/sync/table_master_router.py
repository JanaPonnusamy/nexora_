from fastapi import APIRouter

from modules.sync.table_master_service import (
    promote
)

router = APIRouter(
    prefix="/api/sync/table-master",
    tags=["Sync Table Master"]
)


@router.post("/promote")
def promote_tables():

    return promote()
