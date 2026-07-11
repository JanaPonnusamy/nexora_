"""HTTP routing for the Document Extraction module (prefix /api/document-extraction).

Tenant-scoped throughout (``tenant_id`` required query param), matching the
platform convention. Business rules live in service.py; this file is
validation + HTTP mapping only.
"""

from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from modules.document_extraction import service
from modules.document_extraction.schemas import (
    ExportRequest,
    HeaderPatch,
    ItemPatch,
    ReprocessRequest,
    SaveRequest,
    SupplierAssignRequest,
    SupplierLayoutUpsert,
)

router = APIRouter(prefix="/api/document-extraction", tags=["Document Extraction"])


# --------------------------------------------------------------------------
# 1. Upload
# --------------------------------------------------------------------------

@router.post("/imports")
async def upload_imports(
    files: List[UploadFile] = File(...),
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    group_as_single_invoice: bool = Form(True),
    actor: Optional[str] = Query(None),
):
    contents = [(f.filename, await f.read()) for f in files]
    try:
        imports = service.upload(contents, tenant_id, store_id, group_as_single_invoice, actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"imports": imports}


# --------------------------------------------------------------------------
# 1b. Image Processing — was previously only reachable via reprocess()
#     (from_stage="preprocessing"); exposed directly so the frontend pipeline
#     can run/report/retry it as its own stage, same pattern as ocr/extract/
#     validate below.
# --------------------------------------------------------------------------

@router.post("/imports/{import_id}/preprocess")
def trigger_preprocess(import_id: int, actor: Optional[str] = Query(None)):
    result = service.run_image_processing(import_id, actor)
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


# --------------------------------------------------------------------------
# 2. OCR
# --------------------------------------------------------------------------

@router.post("/imports/{import_id}/ocr")
def trigger_ocr(import_id: int, actor: Optional[str] = Query(None)):
    try:
        return service.run_ocr(import_id, actor)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@router.get("/imports/{import_id}/ocr-raw")
def get_ocr_raw(import_id: int):
    result = service.get_ocr_raw(import_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


# --------------------------------------------------------------------------
# 3. Extract
# --------------------------------------------------------------------------

@router.post("/imports/{import_id}/extract")
def trigger_extract(import_id: int, actor: Optional[str] = Query(None)):
    try:
        return service.run_extraction(import_id, actor)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/imports/{import_id}/extraction")
def get_extraction(import_id: int):
    result = service.get_extraction(import_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


# --------------------------------------------------------------------------
# 4. Validate
# --------------------------------------------------------------------------

@router.post("/imports/{import_id}/validate")
def trigger_validate(import_id: int, actor: Optional[str] = Query(None)):
    try:
        return service.run_validation(import_id, actor)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))


@router.get("/imports/{import_id}/validation")
def get_validation(import_id: int):
    result = service.get_validation(import_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


# --------------------------------------------------------------------------
# 5. Review
# --------------------------------------------------------------------------

@router.get("/imports/{import_id}/original")
def get_original_image(import_id: int, page: int = Query(1, ge=1)):
    result = service.get_original_file(import_id, page)
    if result is None:
        raise HTTPException(status_code=404, detail="Original image not found")
    path, media_type = result
    return FileResponse(path, media_type=media_type)


@router.get("/imports/{import_id}/preview")
def get_preview_image(import_id: int, page: int = Query(1, ge=1)):
    result = service.get_preview_file(import_id, page)
    if result is None:
        raise HTTPException(status_code=404, detail="Preview image not found")
    path, media_type = result
    return FileResponse(path, media_type=media_type)


@router.get("/imports/{import_id}/review")
def get_review(import_id: int):
    result = service.get_review(import_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


@router.patch("/imports/{import_id}/header")
def patch_header(import_id: int, payload: HeaderPatch):
    fields = payload.dict(exclude_unset=True, exclude={"actor"})
    result = service.patch_header(import_id, fields, payload.actor)
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


@router.patch("/imports/{import_id}/items/{item_id}")
def patch_item(import_id: int, item_id: int, payload: ItemPatch):
    fields = payload.dict(exclude_unset=True, exclude={"actor"})
    result = service.patch_item(import_id, item_id, fields, payload.actor)
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return result


@router.post("/imports/{import_id}/items/{item_id}/exclude")
def exclude_item(import_id: int, item_id: int, actor: Optional[str] = Query(None)):
    result = service.exclude_item(import_id, item_id, actor)
    if result is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return result


@router.post("/imports/{import_id}/supplier")
def assign_supplier(import_id: int, payload: SupplierAssignRequest):
    fields = payload.dict(exclude_unset=True, exclude={"actor"})
    result = service.assign_supplier(import_id, fields, payload.actor)
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


# --------------------------------------------------------------------------
# 6. Save
# --------------------------------------------------------------------------

@router.post("/imports/{import_id}/save")
def save_import(import_id: int, payload: SaveRequest):
    try:
        result = service.save(import_id, payload.force, payload.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


# --------------------------------------------------------------------------
# 7. Export
# --------------------------------------------------------------------------

@router.post("/exports", status_code=201)
def create_export(payload: ExportRequest):
    try:
        result = service.export(payload.import_ids, payload.file_format, payload.actor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        **result,
        "download_url": f"/api/document-extraction/exports/{result['export_batch_id']}/download",
    }


@router.get("/exports/{export_batch_id}/download")
def download_export(export_batch_id: str):
    result = service.get_export_file(export_batch_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Export not found")
    content, filename, media_type = result
    return Response(
        content=content, media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------
# 8. History
# --------------------------------------------------------------------------

@router.get("/imports")
def list_imports(
    tenant_id: str = Query(...),
    store_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    supplier_name: Optional[str] = Query(None),
    invoice_number: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    has_errors: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
):
    return service.list_imports(
        tenant_id, store_id=store_id, status=status, supplier_name=supplier_name,
        invoice_number=invoice_number, date_from=date_from, date_to=date_to,
        has_errors=has_errors, page=page, page_size=page_size,
    )


@router.get("/imports/{import_id}")
def get_import_detail(import_id: int):
    result = service.get_import_detail(import_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


@router.get("/imports/{import_id}/corrections")
def list_corrections(
    import_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
):
    return service.list_corrections(import_id, page, page_size)


# --------------------------------------------------------------------------
# 9. Delete
# --------------------------------------------------------------------------

@router.delete("/imports/{import_id}", status_code=204)
def delete_import(import_id: int, actor: Optional[str] = Query(None)):
    deleted = service.delete_import(import_id, actor)
    if not deleted:
        raise HTTPException(status_code=404, detail="Import not found")
    return None


# --------------------------------------------------------------------------
# 10. Reprocess
# --------------------------------------------------------------------------

@router.post("/imports/{import_id}/reprocess")
def reprocess(import_id: int, payload: ReprocessRequest):
    try:
        result = service.reprocess(import_id, payload.from_stage, payload.actor)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


# --------------------------------------------------------------------------
# 11. Supplier Lookup — the Review UI's manual supplier-assignment search box
#     (Chunk 9, Supplier Identification, wired here in Chunk 14)
# --------------------------------------------------------------------------

@router.get("/suppliers/lookup")
def supplier_lookup(
    tenant_id: str = Query(...),
    store_id: str = Query(...),
    gst_number: Optional[str] = Query(None),
    dl_number: Optional[str] = Query(None),
    phone: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
):
    if not any([gst_number, dl_number, phone, name]):
        raise HTTPException(status_code=400, detail="At least one lookup field is required")
    return service.lookup_supplier(tenant_id, store_id, gst_number, dl_number, phone, name)


# --------------------------------------------------------------------------
# 12. Supplier Layout (Settings page)
# --------------------------------------------------------------------------

@router.get("/supplier-layouts")
def list_supplier_layouts(tenant_id: str = Query(...)):
    return service.list_supplier_layouts(tenant_id)


@router.post("/supplier-layouts")
def create_supplier_layout(payload: SupplierLayoutUpsert, tenant_id: str = Query(...)):
    return service.upsert_supplier_layout(
        tenant_id, None, payload.supplier_code, payload.layout_name,
        payload.layout_json, payload.actor,
    )


@router.put("/supplier-layouts/{layout_id}")
def update_supplier_layout(layout_id: int, payload: SupplierLayoutUpsert, tenant_id: str = Query(...)):
    return service.upsert_supplier_layout(
        tenant_id, layout_id, payload.supplier_code, payload.layout_name,
        payload.layout_json, payload.actor,
    )
