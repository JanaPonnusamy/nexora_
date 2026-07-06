from fastapi import APIRouter

from modules.sync.table_registry_service import (
    populate_registry
)

router = APIRouter(
    prefix="/api/sync/table-registry",
    tags=["Sync Table Registry"]
)


@router.post("/populate")
def populate():

    return populate_registry()


