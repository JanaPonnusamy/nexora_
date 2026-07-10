"""Document Extraction — orchestration layer.

Thin glue between router.py and repository.py/storage.py. Business logic
that needs the heavy pipeline (OCR, extraction, validation rules, Excel
export) is stubbed here with NotImplementedError pointing at the
Development Plan chunk that implements it — see
docs/Document_Extraction_DevelopmentPlan.md.
"""

import logging
from datetime import datetime, timezone

from modules.document_extraction import preprocessing, repository, storage
from modules.document_extraction.json_contracts import (
    OriginalFileEntry,
    OriginalFilesContract,
    ProcessedFileEntry,
    ProcessedFilesContract,
)

logger = logging.getLogger("document_extraction.service")


# --------------------------------------------------------------------------
# Upload (Chunk 4) — one import session per invoice, however many files/pages
# --------------------------------------------------------------------------

def upload(files, tenant_id, store_id, group_as_single_invoice, uploaded_by):
    """`files` is a list of (filename, content_bytes) tuples.

    One invoice may arrive as multiple JPGs, multiple PDF pages, or a mixed
    batch — group_as_single_invoice=True (the default whenever >1 file is
    posted together) keeps all of them under ONE doc_import row with a
    recorded page order (OriginalFiles contract). It is never split into
    multiple imports unless the caller explicitly says each file is its own
    invoice. Duplicate-file detection is a soft flag only — never rejects
    the upload."""
    if not files:
        raise ValueError("At least one file is required")

    if group_as_single_invoice or len(files) == 1:
        return [_create_single_import(files, tenant_id, store_id, uploaded_by)]

    return [
        _create_single_import([f], tenant_id, store_id, uploaded_by)
        for f in files
    ]


def _create_single_import(files, tenant_id, store_id, uploaded_by):
    source_type = storage.source_type_for_filename(files[0][0])
    checksum = storage.compute_combined_checksum([content for _, content in files])

    # import_id doesn't exist until after INSERT, but storage paths are keyed
    # by it — insert first with a placeholder path, then write the file(s)
    # into that id's folder and finalize with set_original_files().
    import_id = repository.create_import(
        tenant_id=tenant_id, store_id=store_id, source_type=source_type,
        original_file_path="", original_file_checksum=checksum,
        uploaded_by=uploaded_by,
    )

    page_entries = []
    for page_no, (filename, content) in enumerate(files, start=1):
        storage_path = storage.save_original(import_id, filename, content)
        page_entries.append(OriginalFileEntry(
            page_no=page_no, original_file_name=filename, storage_path=storage_path,
            display_order=page_no,
        ))
    original_files = OriginalFilesContract(files=page_entries)

    # exclude_import_id=import_id: the checksum was already written by
    # create_import() above, so without excluding ourselves this would match
    # the row we just inserted and silently report every upload as unique.
    duplicate_of = repository.find_duplicate_by_checksum(
        tenant_id, store_id, checksum, exclude_import_id=import_id,
    )
    is_duplicate = duplicate_of is not None

    # A multi-file image upload's page count is known now (one file = one
    # page); a single PDF's real page count is only known after Chunk 5
    # splits it, so leave it unset here.
    known_page_count = len(files) if source_type != "PDF" else None

    repository.set_original_files(
        import_id,
        original_file_path=page_entries[0].storage_path,
        original_files_json=original_files.model_dump(),
        is_duplicate=is_duplicate,
        duplicate_of_import_id=duplicate_of,
        page_count=known_page_count,
    )

    logger.info("document_extraction.upload import_id=%s pages=%d", import_id, len(files))
    return repository.get_import(import_id)


# --------------------------------------------------------------------------
# Image Processing (Chunk 5) — real. PDF -> pages via preprocessing.py,
# image upload -> each original page loaded directly; every page then runs
# the rotate/deskew/denoise/contrast/border chain and is saved to preview/.
# No OCR is invoked here or imported by preprocessing.py.
# --------------------------------------------------------------------------

def run_image_processing(import_id, actor=None):
    doc = repository.get_import(import_id)
    if not doc:
        return None

    try:
        source_pages = _load_source_pages(doc)
    except Exception as exc:
        repository.update_import_fields(import_id, {
            "status": "FAILED",
            "failure_reason": f"Could not load source page(s) for preprocessing: {exc}",
        })
        logger.warning("document_extraction.preprocess import_id=%s: load failed: %s", import_id, exc)
        return repository.get_import(import_id)

    processed_entries = []
    failures = 0
    for page_no, image in source_pages:
        try:
            processed_image, meta = preprocessing.process_page(image)
            content = preprocessing.encode_image(processed_image)
            processed_path = storage.save_preview(import_id, page_no, content)
            processed_entries.append(ProcessedFileEntry(
                page_no=page_no, processed_storage_path=processed_path,
                processing_status="DONE", **meta,
            ))
        except Exception as exc:
            failures += 1
            logger.warning(
                "document_extraction.preprocess import_id=%s page=%s failed: %s",
                import_id, page_no, exc,
            )
            processed_entries.append(ProcessedFileEntry(
                page_no=page_no, processed_storage_path=None,
                processing_status="FAILED", processing_notes=str(exc),
            ))

    processed_files = ProcessedFilesContract(files=processed_entries)

    if source_pages and failures == len(source_pages):
        repository.update_import_fields(import_id, {
            "status": "FAILED",
            "failure_reason": "Image preprocessing failed for every page",
            "processed_files_json": processed_files.model_dump(),
        })
        logger.info("document_extraction.preprocess import_id=%s: all %d page(s) failed", import_id, failures)
        return repository.get_import(import_id)

    preview_path = next(
        (e.processed_storage_path for e in processed_entries if e.processing_status == "DONE"),
        None,
    )
    repository.update_import_fields(import_id, {
        "processed_files_json": processed_files.model_dump(),
        "preview_image_path": preview_path,
        "page_count": len(source_pages),
        "is_image_processed": True,
    })
    logger.info(
        "document_extraction.preprocess import_id=%s pages=%d failures=%d",
        import_id, len(source_pages), failures,
    )
    return repository.get_import(import_id)


def _load_source_pages(doc):
    """Returns [(page_no, image_bgr), ...] for an import — splits the PDF
    if source_type is PDF, otherwise loads each OriginalFiles entry as its
    own page (an image upload's pages are already discrete files)."""
    if doc["source_type"] == "PDF":
        pdf_path = storage.absolute_path(doc["original_file_path"])
        page_images = preprocessing.pdf_to_images(pdf_path)
        return list(enumerate(page_images, start=1))

    original_files = doc.get("original_files_json") or {"files": []}
    pages = []
    for entry in original_files.get("files", []):
        image = preprocessing.load_image_from_path(storage.absolute_path(entry["storage_path"]))
        pages.append((entry["page_no"], image))
    return pages


# --------------------------------------------------------------------------
# Pipeline stages (Chunks 6-10) — stubbed
# --------------------------------------------------------------------------

def run_ocr(import_id, actor=None):
    raise NotImplementedError("OCR engine is implemented in Chunk 6 (OCR Engine)")


def get_ocr_raw(import_id):
    doc = repository.get_import(import_id)
    if not doc:
        return None
    return {"import_id": import_id, "ocr_json": doc.get("ocr_json")}


def run_extraction(import_id, actor=None):
    raise NotImplementedError(
        "Supplier detection / header / item extraction are implemented in "
        "Chunks 7-9 (Supplier Detection, Header Extraction, Product Extraction)"
    )


def get_extraction(import_id):
    doc = repository.get_import(import_id)
    if not doc:
        return None
    items = repository.list_items(import_id)
    return {
        "import_id": import_id,
        "status": doc["status"],
        "supplier": {
            k: doc[k] for k in (
                "matched_supplier_code", "supplier_name", "gst_number", "dl_number",
                "supplier_match_method", "supplier_match_confidence", "is_supplier_unknown",
            )
        },
        "header": doc,
        "items": items,
    }


def run_validation(import_id, actor=None):
    raise NotImplementedError("Validation rules are implemented in Chunk 10 (Validation)")


def get_validation(import_id):
    doc = repository.get_import(import_id)
    if not doc:
        return None
    return {
        "import_id": import_id,
        "validation_status": doc["validation_status"],
        "findings": doc.get("validation_json") or [],
    }


# --------------------------------------------------------------------------
# Review (Chunk 11)
# --------------------------------------------------------------------------

def get_review(import_id):
    extraction = get_extraction(import_id)
    if not extraction:
        return None
    validation = get_validation(import_id)
    doc = extraction["header"]
    return {
        **extraction,
        "validation": validation,
        "preview_image_path": doc.get("preview_image_path"),
    }


def patch_header(import_id, fields: dict, actor):
    fields = {k: v for k, v in fields.items() if k != "actor" and v is not None}
    if not fields:
        return repository.get_import(import_id)

    before = repository.get_import(import_id)
    if not before:
        return None

    repository.update_import_fields(import_id, fields)

    for field_name, new_value in fields.items():
        old_value = before.get(field_name)
        if str(old_value) != str(new_value):
            repository.insert_review_entry(
                import_id, None, field_name, old_value, new_value, actor,
            )

    return repository.get_import(import_id)


def patch_item(import_id, item_id, fields: dict, actor):
    fields = {k: v for k, v in fields.items() if k != "actor" and v is not None}
    before = repository.get_item(item_id)
    if not before or before["import_id"] != import_id:
        return None
    if not fields:
        return before

    repository.update_item_fields(item_id, fields)

    for field_name, new_value in fields.items():
        old_value = before.get(field_name)
        if str(old_value) != str(new_value):
            repository.insert_review_entry(
                import_id, item_id, field_name, old_value, new_value, actor,
            )

    return repository.get_item(item_id)


def exclude_item(import_id, item_id, actor):
    item = repository.get_item(item_id)
    if not item or item["import_id"] != import_id:
        return None
    repository.update_item_fields(item_id, {"is_excluded": True})
    repository.insert_review_entry(import_id, item_id, "is_excluded", False, True, actor)
    return repository.get_item(item_id)


def assign_supplier(import_id, fields: dict, actor):
    fields = {k: v for k, v in fields.items() if k != "actor" and v is not None}
    fields["supplier_match_method"] = "MANUAL"
    fields["is_supplier_unknown"] = False
    before = repository.get_import(import_id)
    if not before:
        return None
    repository.update_import_fields(import_id, fields)
    for field_name, new_value in fields.items():
        repository.insert_review_entry(
            import_id, None, field_name, before.get(field_name), new_value, actor,
        )
    return repository.get_import(import_id)


# --------------------------------------------------------------------------
# Save (Chunk 12)
# --------------------------------------------------------------------------

def save(import_id, force, actor):
    doc = repository.get_import(import_id)
    if not doc:
        return None
    if doc["validation_status"] == "FAILED" and not force:
        raise ValueError(
            "Import has unresolved validation errors; pass force=true to save anyway"
        )
    if doc["validation_status"] == "FAILED" and force:
        repository.insert_review_entry(
            import_id, None, "validation_override", "FAILED", "forced", actor,
        )

    now = datetime.now(timezone.utc)
    repository.update_import_fields(import_id, {
        "status": "SAVED", "reviewed_by": actor, "reviewed_at": now, "saved_at": now,
    })
    return repository.get_import(import_id)


# --------------------------------------------------------------------------
# Export (Chunk 13) — stubbed
# --------------------------------------------------------------------------

def export(import_ids, file_format, actor):
    raise NotImplementedError("Excel/CSV export is implemented in Chunk 13 (Excel Export)")


def list_export_history(import_id):
    return repository.list_export_history(import_id)


# --------------------------------------------------------------------------
# History (Chunk 14)
# --------------------------------------------------------------------------

def list_imports(tenant_id, **filters):
    page = filters.pop("page", 1)
    page_size = filters.pop("page_size", 25)
    rows, total = repository.list_imports(tenant_id, page=page, page_size=page_size, **filters)
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


def get_import_detail(import_id):
    doc = repository.get_import(import_id)
    if not doc:
        return None
    return {
        "import": doc,
        "items": repository.list_items(import_id),
        "exports": repository.list_export_history(import_id),
    }


# --------------------------------------------------------------------------
# Corrections (Chunk 15)
# --------------------------------------------------------------------------

def list_corrections(import_id, page=1, page_size=100):
    rows, total = repository.list_corrections(import_id, page, page_size)
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


# --------------------------------------------------------------------------
# Delete / Reprocess (Chunk 16) — delete is real, reprocess needs the pipeline
# --------------------------------------------------------------------------

def delete_import(import_id, actor):
    return repository.soft_delete_import(import_id, actor)


def reprocess(import_id, from_stage, actor):
    raise NotImplementedError(
        "Reprocess re-invokes the pipeline (Chunks 5-10); implemented once "
        "those stages exist (Chunk 16, Integration)"
    )


# --------------------------------------------------------------------------
# Supplier layouts (Settings page)
# --------------------------------------------------------------------------

def list_supplier_layouts(tenant_id):
    return repository.list_supplier_layouts(tenant_id)


def upsert_supplier_layout(tenant_id, layout_id, supplier_code, layout_name, layout_json, actor):
    new_id = repository.upsert_supplier_layout(
        layout_id, tenant_id, supplier_code, layout_name, layout_json, actor,
    )
    return {"layout_id": new_id}
