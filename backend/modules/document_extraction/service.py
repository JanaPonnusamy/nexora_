"""Document Extraction — orchestration layer.

Thin glue between router.py and repository.py/storage.py/the pipeline
engines (parser, table_engine, header_engine, supplier_engine,
product_resolution). run_ocr/run_extraction/run_validation (Chunk 14,
Integration) are the only place those engines get wired together — nothing
downstream (router.py, the frontend) talks to an engine directly.
"""

import calendar
import logging
import re
import uuid
from datetime import date, datetime, timezone

from modules.document_extraction import (
    export_excel,
    page_merge,
    preprocessing,
    product_resolution,
    repository,
    storage,
)
from modules.document_extraction.header_engine import HeaderExtractionEngine
from modules.document_extraction.invoice_boundary import detect_invoice_groups
from modules.document_extraction.json_contracts import (
    ExportInfoContract,
    OriginalFileEntry,
    OriginalFilesContract,
    ProcessedFileEntry,
    ProcessedFilesContract,
    ValidationFinding,
)
from modules.document_extraction.json_contracts import BBox as ContractBBox
from modules.document_extraction.json_contracts import OCRLine as ContractOCRLine
from modules.document_extraction.json_contracts import OCRPage as ContractOCRPage
from modules.document_extraction.json_contracts import OCRResultContract
from modules.document_extraction.json_contracts import OCRWord as ContractOCRWord
from modules.document_extraction.ocr.factory import OCRFactory
from modules.document_extraction.ocr.models import BoundingBox, Confidence, OCRDocument
from modules.document_extraction.ocr.models import OCRLine as EngineOCRLine
from modules.document_extraction.ocr.models import OCRPage as EngineOCRPage
from modules.document_extraction.ocr.models import OCRWord as EngineOCRWord
from modules.document_extraction.supplier_engine import SupplierIdentificationEngine
from modules.document_extraction.supplier_engine import supplier_master_repository

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

    _verify_upload_parts(files)

    if group_as_single_invoice or len(files) == 1:
        return [_create_single_import(files, tenant_id, store_id, uploaded_by)]

    return [
        _create_single_import([f], tenant_id, store_id, uploaded_by)
        for f in files
    ]


def _verify_upload_parts(files):
    """Every part of a multi-part upload must be readable BEFORE any import
    row exists. A page that arrived truncated (a common WhatsApp/phone-
    transfer failure) is invisible until OCR reaches it, and by then the
    invoice is already half-imported — the operator sees "extraction failed"
    with no clue which of their 4 photos was the bad one. Rejecting the whole
    batch up front, naming the file, means the fix is "re-upload that page".
    """
    bad_parts = []
    for filename, content in files:
        try:
            source_type = storage.source_type_for_filename(filename)
        except ValueError as exc:
            bad_parts.append(str(exc))
            continue
        if not content:
            bad_parts.append(f"'{filename}' is empty (0 bytes)")
        elif source_type == "PDF":
            if not content.lstrip()[:5].startswith(b"%PDF"):
                bad_parts.append(f"'{filename}' is not a readable PDF")
        elif not preprocessing.is_readable_image(content):
            bad_parts.append(f"'{filename}' could not be decoded as an image (truncated or corrupt)")

    if bad_parts:
        raise ValueError(
            f"{len(bad_parts)} of {len(files)} uploaded file(s) could not be read: "
            + "; ".join(bad_parts)
            + ". Re-upload the affected page(s)."
        )


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
        written = storage.absolute_path(storage_path)
        if not written.exists() or written.stat().st_size != len(content):
            raise ValueError(
                f"'{filename}' (page {page_no}) was not written to storage completely; "
                "re-upload this page."
            )
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
# Pipeline stages (Chunk 14 — Integration)
# --------------------------------------------------------------------------

def run_ocr(import_id, actor=None):
    doc = repository.get_import(import_id)
    if not doc:
        return None

    try:
        page_paths = _ocr_input_pages(doc)
        if not page_paths:
            raise ValueError("No processed or original page images available for OCR")
        ocr_document = OCRFactory.create().extract(page_paths)
    except Exception as exc:
        repository.update_import_fields(import_id, {
            "status": "FAILED", "failure_reason": f"OCR failed: {exc}",
        })
        logger.warning("document_extraction.ocr import_id=%s failed: %s", import_id, exc)
        return repository.get_import(import_id)

    groups = detect_invoice_groups(ocr_document)
    split_import_ids = []
    if len(groups) > 1:
        logger.info(
            "document_extraction.ocr import_id=%s: %d invoices bundled in one upload (pages %s), splitting",
            import_id, len(groups), groups,
        )
        for extra_group in groups[1:]:
            new_import_id = _split_off_invoice_group(doc, ocr_document, extra_group, actor)
            split_import_ids.append(new_import_id)
            logger.info(
                "document_extraction.ocr import_id=%s: split page(s) %s into new import_id=%s",
                import_id, extra_group, new_import_id,
            )
        page_no_map = {old: new for new, old in enumerate(groups[0], start=1)}
        _trim_import_to_pages(import_id, doc, page_no_map)
        ocr_document = _renumber_pages(ocr_document, page_no_map)

    contract = _ocr_document_to_contract(ocr_document)
    repository.update_import_fields(import_id, {
        "ocr_json": contract.model_dump(),
        "ocr_confidence": round((contract.average_confidence or 0.0) * 100, 2),
        "is_ocr_completed": True,
        "page_count": len(ocr_document.pages),
    })
    logger.info("document_extraction.ocr import_id=%s pages=%d", import_id, len(ocr_document.pages))

    # Each split-off invoice is carried through extraction + validation here,
    # not left for a caller to notice and drive. The frontend pipeline only
    # ever tracks the import it uploaded (the primary), so an invoice split
    # out of that upload and left at UPLOADED would simply never be extracted
    # by anyone — it would sit in History as an empty import forever.
    for new_import_id in split_import_ids:
        run_extraction(new_import_id, actor)
        run_validation(new_import_id, actor)

    result = repository.get_import(import_id)
    result["split_import_ids"] = split_import_ids
    return result


def _renumber_pages(ocr_document, page_no_map):
    return ocr_document.model_copy(update={
        "pages": [
            page.model_copy(update={"page_no": page_no_map[page.page_no]})
            for page in ocr_document.pages if page.page_no in page_no_map
        ],
    })


def _split_off_invoice_group(doc, ocr_document, page_nos, actor):
    """Creates a new import for `page_nos` (pages that invoice_boundary
    detected as belonging to a DIFFERENT invoice than the rest of this
    upload), copying their original/processed files across and renumbering
    pages to start at 1. Returns the new import_id. See run_ocr, the only
    caller — the calling import is trimmed down to its own remaining pages
    separately via _trim_import_to_pages."""
    page_no_map = {old: new for new, old in enumerate(sorted(page_nos), start=1)}

    original_files = (doc.get("original_files_json") or {}).get("files", [])
    kept_originals = sorted(
        (e for e in original_files if e["page_no"] in page_no_map),
        key=lambda e: e["page_no"],
    )
    processed_files = (doc.get("processed_files_json") or {}).get("files", [])
    kept_processed = sorted(
        (e for e in processed_files if e["page_no"] in page_no_map),
        key=lambda e: e["page_no"],
    )

    checksum = storage.compute_combined_checksum(
        storage.absolute_path(e["storage_path"]).read_bytes() for e in kept_originals
    )
    new_import_id = repository.create_import(
        doc["tenant_id"], doc.get("store_id"), doc["source_type"],
        original_file_path="", original_file_checksum=checksum,
        uploaded_by=actor or doc.get("uploaded_by"),
    )

    new_original_entries = []
    for entry in kept_originals:
        new_page_no = page_no_map[entry["page_no"]]
        new_path = storage.copy_into_import(entry["storage_path"], new_import_id, "original")
        new_original_entries.append({
            **entry, "page_no": new_page_no, "storage_path": new_path, "display_order": new_page_no,
        })

    new_processed_entries = []
    for entry in kept_processed:
        new_path = (
            storage.copy_into_import(entry["processed_storage_path"], new_import_id, "preview")
            if entry.get("processed_storage_path") else None
        )
        new_processed_entries.append({
            **entry, "page_no": page_no_map[entry["page_no"]], "processed_storage_path": new_path,
        })

    repository.set_original_files(
        new_import_id,
        original_file_path=new_original_entries[0]["storage_path"] if new_original_entries else None,
        original_files_json={"files": new_original_entries},
        is_duplicate=False, duplicate_of_import_id=None,
        page_count=len(new_original_entries),
    )
    preview_path = next(
        (e["processed_storage_path"] for e in new_processed_entries if e.get("processing_status") == "DONE"),
        None,
    )
    repository.update_import_fields(new_import_id, {
        "processed_files_json": {"files": new_processed_entries},
        "preview_image_path": preview_path,
        "is_image_processed": bool(new_processed_entries),
    })

    group_document = ocr_document.model_copy(update={
        "pages": [
            page.model_copy(update={"page_no": page_no_map[page.page_no]})
            for page in ocr_document.pages if page.page_no in page_no_map
        ],
    })
    group_contract = _ocr_document_to_contract(group_document)
    repository.update_import_fields(new_import_id, {
        "ocr_json": group_contract.model_dump(),
        "ocr_confidence": round((group_contract.average_confidence or 0.0) * 100, 2),
        "is_ocr_completed": True,
    })
    return new_import_id


def _trim_import_to_pages(import_id, doc, page_no_map):
    """Rewrites `import_id`'s own original/processed file lists down to just
    the pages in `page_no_map` (old page_no -> new page_no) after the other
    pages were split off into new imports (see _split_off_invoice_group).

    The kept group is the one containing page 1, but it is NOT necessarily
    contiguous — a batch photographed out of order can leave this import
    holding pages 1, 3 and 4 while page 2 belongs to a different invoice —
    so the kept pages are renumbered 1..N here, exactly as the split-off
    group is."""
    original_files = (doc.get("original_files_json") or {}).get("files", [])
    kept_originals = [
        {**e, "page_no": page_no_map[e["page_no"]], "display_order": page_no_map[e["page_no"]]}
        for e in original_files if e["page_no"] in page_no_map
    ]
    kept_originals.sort(key=lambda e: e["page_no"])
    processed_files = (doc.get("processed_files_json") or {}).get("files", [])
    kept_processed = [
        {**e, "page_no": page_no_map[e["page_no"]]}
        for e in processed_files if e["page_no"] in page_no_map
    ]
    kept_processed.sort(key=lambda e: e["page_no"])
    preview_path = next(
        (e["processed_storage_path"] for e in kept_processed if e.get("processing_status") == "DONE"),
        None,
    )
    repository.set_original_files(
        import_id,
        original_file_path=kept_originals[0]["storage_path"] if kept_originals else doc.get("original_file_path"),
        original_files_json={"files": kept_originals},
        is_duplicate=bool(doc.get("is_duplicate")),
        duplicate_of_import_id=doc.get("duplicate_of_import_id"),
        page_count=len(kept_originals),
    )
    repository.update_import_fields(import_id, {
        "processed_files_json": {"files": kept_processed},
        "preview_image_path": preview_path,
    })


def _ocr_input_pages(doc):
    """Processed (Chunk 5) pages if available, else the raw originals —
    OCR should always prefer the deskewed/denoised version, but must still
    work if image preprocessing hasn't run (e.g. reprocess from_stage='ocr'
    on an import that never got a preprocessing pass)."""
    processed = (doc.get("processed_files_json") or {}).get("files", [])
    paths = [
        storage.absolute_path(e["processed_storage_path"])
        for e in sorted(processed, key=lambda e: e["page_no"])
        if e.get("processing_status") == "DONE" and e.get("processed_storage_path")
    ]
    if paths:
        return paths
    original = (doc.get("original_files_json") or {}).get("files", [])
    return [
        storage.absolute_path(e["storage_path"])
        for e in sorted(original, key=lambda e: e["page_no"])
        if e.get("storage_path")
    ]


def _ocr_document_to_contract(document: OCRDocument) -> OCRResultContract:
    """OCRDocument (rich, in-process — ocr/models.py) -> OCRResultContract
    (flat, storage — json_contracts.py). See json_contracts.py's docstring
    for why these are deliberately two different shapes."""
    pages = []
    for page in document.pages:
        lines = []
        for line in page.lines:
            words = [
                ContractOCRWord(text=w.text, confidence=w.confidence.score, bbox=_to_contract_bbox(w.bbox))
                for w in line.words
            ]
            lines.append(ContractOCRLine(
                line_no=line.line_no, text=line.text, confidence=line.confidence.score,
                bbox=_to_contract_bbox(line.bbox), words=words,
            ))
        pages.append(ContractOCRPage(page_no=page.page_no, lines=lines))
    return OCRResultContract(
        engine_name=document.engine_name, engine_version=document.engine_version,
        pages=pages,
        average_confidence=document.average_confidence.score if document.average_confidence else None,
    )


def _contract_to_ocr_document(contract: OCRResultContract) -> OCRDocument:
    """The reverse of _ocr_document_to_contract — rebuilds the rich
    in-process model from what's stored in doc_import.ocr_json, so
    run_extraction can run independently of run_ocr (e.g. on reprocess)
    without re-running OCR itself. width_px/height_px are placeholders (0)
    since the storage contract doesn't carry per-page pixel dimensions —
    nothing downstream of here (parser, table_engine, header_engine) reads
    them."""
    pages = []
    for page in contract.pages:
        lines = []
        for line in page.lines:
            words = [
                EngineOCRWord(text=w.text, confidence=Confidence(score=w.confidence), bbox=_to_engine_bbox(w.bbox))
                for w in line.words
            ]
            lines.append(EngineOCRLine(
                line_no=line.line_no, text=line.text, confidence=Confidence(score=line.confidence),
                bbox=_to_engine_bbox(line.bbox), words=words,
            ))
        pages.append(EngineOCRPage(page_no=page.page_no, width_px=0, height_px=0, lines=lines))
    return OCRDocument(
        engine_name=contract.engine_name, engine_version=contract.engine_version, pages=pages,
        average_confidence=Confidence(score=contract.average_confidence) if contract.average_confidence is not None else None,
    )


def _to_contract_bbox(bbox: BoundingBox) -> ContractBBox:
    return ContractBBox(x1=bbox.x1, y1=bbox.y1, x2=bbox.x2, y2=bbox.y2)


def _to_engine_bbox(bbox: ContractBBox) -> BoundingBox:
    return BoundingBox(x1=bbox.x1, y1=bbox.y1, x2=bbox.x2, y2=bbox.y2)


def get_ocr_raw(import_id):
    doc = repository.get_import(import_id)
    if not doc:
        return None
    return {"import_id": import_id, "ocr_json": doc.get("ocr_json")}


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EXPIRY_RE = re.compile(r"^(0?[1-9]|1[0-2])[/-](\d{2}|\d{4})$")


def _iso_date_or_none(value):
    """Only ever write a real, parsed date into a DATE column — an
    unparseable raw string (kept on the header_engine result specifically
    so nothing is silently lost, see header_engine's docstring) stays out of
    doc_import.invoice_date/ack_date rather than erroring the whole
    extraction on a SQL type-conversion failure."""
    return value if value and _ISO_DATE_RE.match(value) else None


def _first_int(text):
    if not text:
        return None
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def _parse_expiry_date(expiry_raw):
    """MM/YY or MM/YYYY -> the last calendar day of that month (standard
    pharma convention: stock is valid through the end of its expiry
    month), as an ISO date string. None if it doesn't match that shape at
    all — expiry_raw stays the only record of it, same reasoning as
    _iso_date_or_none."""
    if not expiry_raw:
        return None
    match = _EXPIRY_RE.match(expiry_raw.strip())
    if not match:
        return None
    month = int(match.group(1))
    year = int(match.group(2))
    if year < 100:
        year += 2000
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, last_day).isoformat()


def run_extraction(import_id, actor=None):
    doc = repository.get_import(import_id)
    if not doc:
        return None
    if not doc.get("ocr_json"):
        raise ValueError("OCR must complete before extraction can run")

    try:
        contract = OCRResultContract(**doc["ocr_json"])
        ocr_document = _contract_to_ocr_document(contract)

        # Page by page, then merged — never one parse across all pages. See
        # page_merge.py for why (a multi-page invoice reprints its header and
        # footer on every page, so a whole-document parse lets page 3's
        # reprinted boilerplate win header fields over page 1's real values).
        pages = page_merge.extract_pages(ocr_document)
        invoice_document = page_merge.merge_document(pages, ocr_document)
        merged_rows = page_merge.merge_rows(pages)

        header_result = HeaderExtractionEngine().extract(invoice_document)
        supplier_match = SupplierIdentificationEngine().identify(
            doc["tenant_id"], doc.get("store_id"), invoice_document.supplier_block, invoice_document.header,
        )

        header_fields = _header_result_to_import_fields(header_result, supplier_match, invoice_document)

        # Resolved (and integrity-checked — see _resolve_and_build_item)
        # before anything is written, so a ProductCodeIntegrityError fails
        # the whole extraction the same graceful way as an OCR/parse error,
        # rather than a partial write followed by an unhandled 500.
        item_rows = [
            _resolve_and_build_item(row, doc["tenant_id"], doc.get("store_id"), supplier_match.matched_supplier_code)
            for row in merged_rows
        ]
    except Exception as exc:
        repository.update_import_fields(import_id, {
            "status": "FAILED", "failure_reason": f"Extraction failed: {exc}",
        })
        logger.warning("document_extraction.extract import_id=%s failed: %s", import_id, exc)
        return repository.get_import(import_id)

    try:
        repository.update_import_fields(import_id, header_fields)
        repository.delete_items_for_import(import_id)
        repository.insert_items(doc["tenant_id"], import_id, item_rows)
    except Exception as exc:
        # A bad OCR number that still slipped past _bounded() (e.g. a value
        # that overflows its DECIMAL column) must fail this import the same
        # graceful, reportable way as any other extraction error — the
        # frontend pipeline shows a failed stage it can retry, instead of a
        # raw 500 with the whole batch's progress lost.
        repository.update_import_fields(import_id, {
            "status": "FAILED", "failure_reason": f"Extraction failed while saving: {exc}",
        })
        logger.warning("document_extraction.extract import_id=%s save failed: %s", import_id, exc)
        return repository.get_import(import_id)

    repository.update_import_fields(import_id, {
        "status": "EXTRACTED", "is_header_extracted": True, "is_items_extracted": True,
    })
    logger.info("document_extraction.extract import_id=%s items=%d", import_id, len(item_rows))
    return repository.get_import(import_id)


def _header_result_to_import_fields(header_result, supplier_match, invoice_document):
    h = header_result.header
    block = invoice_document.supplier_block
    return {
        "ocr_supplier_name": block.candidate_name if block else None,
        "supplier_name": h.supplier_name,
        "gst_number": h.gst_number,
        "dl_number": h.dl_number,
        "supplier_phone": block.candidate_phone if block else None,
        "supplier_address": block.candidate_address if block else None,
        "matched_supplier_code": supplier_match.matched_supplier_code,
        "supplier_match_method": "UNKNOWN" if supplier_match.is_unknown else supplier_match.matched_field,
        "supplier_match_confidence": round(supplier_match.confidence.score * 100, 2),
        "is_supplier_unknown": supplier_match.is_unknown,
        "ocr_invoice_number": invoice_document.header.invoice_number,
        "invoice_number": h.invoice_number,
        "ocr_invoice_date": invoice_document.header.invoice_date,
        "invoice_date": _iso_date_or_none(h.invoice_date),
        "invoice_type": h.invoice_type,
        "order_number": h.order_number,
        "transport": h.transport,
        "salesman": h.salesman,
        "credit_days": _first_int(h.credit_days),
        "gross_amount": h.gross_amount,
        "discount_amount": h.discount_amount,
        "scheme_discount": h.scheme_discount,
        "cash_discount": h.cash_discount,
        "taxable_amount": h.taxable_amount,
        "cgst_amount": h.cgst_amount,
        "sgst_amount": h.sgst_amount,
        "igst_amount": h.igst_amount,
        "cess_amount": h.cess_amount,
        "round_off": h.round_off,
        "net_amount": h.net_amount,
        "item_count": h.item_count,
        "total_quantity": h.total_quantity,
        "irn_number": h.irn_number,
        "ack_number": h.ack_number,
        "ack_date": _iso_date_or_none(h.ack_date),
        "gst_slab_breakup_json": [g.model_dump() for g in invoice_document.gst_summary],
    }


def _resolve_and_build_item(row, tenant_id, store_id, supplier_code):
    product_code = product_guid = product_code_source = None
    if row.product_name:
        result = product_resolution.resolve_product(product_resolution.ProductResolutionRequest(
            tenant_id=tenant_id, store_id=store_id, ocr_product_name=row.product_name,
            supplier_code=supplier_code,
        ))
        # ProductCode Integrity Rule (service layer, no SQL FK — see
        # product_resolution.validate_product_code_integrity): confirms the
        # code resolve_product() just returned actually exists in the table
        # its source claims, before it's ever written to doc_import_item.
        product_resolution.validate_product_code_integrity(
            tenant_id, store_id, result.product_code, result.source,
        )
        product_code, product_guid, product_code_source = result.product_code, result.product_guid, result.source

    return {
        "line_number": row.line_number,
        "product_code": product_code,
        "product_code_source": product_code_source,
        "product_guid": product_guid,
        "ocr_product_name": row.product_name or row.ocr_row_text,
        "normalized_product_name": row.product_name,
        "pack": row.pack,
        "hsn_code": row.hsn,
        "batch_number": row.batch,
        "expiry_raw": row.expiry,
        "expiry_date": _parse_expiry_date(row.expiry),
        "quantity": _bounded(row.qty, 10 ** 12),
        "free_quantity": _bounded(row.free_qty, 10 ** 12),
        "ptr": _bounded(row.ptr, 10 ** 12),
        "purchase_rate": _bounded(row.purchase_rate, 10 ** 12),
        "mrp": _bounded(row.mrp, 10 ** 12),
        "gst_percent": _bounded(row.gst_percent, 100),
        "discount_percent": _bounded(row.discount_percent, 100),
        # StructuredProductRow has no separate discount-AMOUNT field (only
        # discount_percent) — leaving this None rather than deriving it from
        # an unconfirmed formula (e.g. amount/(1-disc%) has rounding/order-
        # of-operations ambiguity the chunk brief doesn't resolve).
        "discount_amount": None,
        "amount": _bounded(row.amount, 10 ** 14),
        "confidence": round(row.confidence.score * 100, 2) if row.confidence else None,
    }


def _bounded(value, max_abs):
    """Drops a numeric cell whose value can't be real for that column — an
    HSN code or batch number that the column aligner landed in the GST%
    column reads as e.g. 30049099, which is not a GST rate and, worse,
    overflows its DECIMAL(5,2) column and takes the whole import down with a
    SQL arithmetic-overflow error. A cell we know is wrong is worth less than
    an empty cell the reviewer can fill in: the row itself is kept, with that
    one field cleared and flagged for Review as a missing value."""
    if value is None:
        return None
    return value if abs(value) <= max_abs else None


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
    """Re-derivable from doc_import/doc_import_item's own columns (not from
    any engine's in-memory result) — deliberately stateless, so it can be
    re-run any time (including via reprocess) without depending on
    run_extraction having just executed in the same request."""
    doc = repository.get_import(import_id)
    if not doc:
        return None
    items = repository.list_items(import_id)
    findings = _build_validation_findings(doc, items)
    severities = {f.severity for f in findings}
    status = "FAILED" if "ERROR" in severities else ("WARNING" if "WARNING" in severities else "PASSED")
    repository.update_import_fields(import_id, {
        "validation_status": status,
        "validation_json": [f.model_dump() for f in findings],
    })
    logger.info(
        "document_extraction.validate import_id=%s status=%s findings=%d",
        import_id, status, len(findings),
    )
    return repository.get_import(import_id)


def _build_validation_findings(doc, items):
    findings = []
    if doc.get("is_supplier_unknown"):
        findings.append(ValidationFinding(
            rule_code="UNKNOWN_SUPPLIER", severity="WARNING",
            message="Supplier could not be matched automatically; assign manually in Review.",
        ))
    for field_name, label in (
        ("invoice_number", "Invoice Number"), ("invoice_date", "Invoice Date"), ("net_amount", "Net Amount"),
    ):
        if doc.get(field_name) is None:
            findings.append(ValidationFinding(
                rule_code="MISSING_REQUIRED_FIELD", severity="ERROR", field=field_name,
                message=f"{label} is missing.",
            ))
    for item in items:
        if item.get("is_excluded"):
            continue
        if not item.get("product_code"):
            findings.append(ValidationFinding(
                rule_code="MISSING_PRODUCT_CODE", severity="WARNING", item_id=item["item_id"],
                message="Product could not be resolved to a ProductCode.",
            ))
        batch = (item.get("batch_number") or "").strip()
        if len(batch) < 2 or not any(c.isalnum() for c in batch):
            findings.append(ValidationFinding(
                rule_code="INVALID_BATCH", severity="WARNING", field="batch_number", item_id=item["item_id"],
                message="Batch number looks invalid or missing.",
            ))
        if item.get("expiry_date") is None and item.get("expiry_raw"):
            findings.append(ValidationFinding(
                rule_code="INVALID_EXPIRY", severity="WARNING", field="expiry_raw", item_id=item["item_id"],
                message=f"Expiry '{item['expiry_raw']}' could not be parsed.",
            ))
    return findings


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
# Export (Chunk 12)
# --------------------------------------------------------------------------

def export(import_ids, file_format, actor):
    """One workbook (or CSV) per call, covering every id in `import_ids` —
    see Document_Extraction_Excel_Contract.md. Missing/deleted ids are
    silently skipped rather than failing the whole batch; raises ValueError
    only if NONE of the requested ids resolve to a real import."""
    imports = repository.get_imports_by_ids(import_ids)
    if not imports:
        raise ValueError("No matching imports found for export")
    order = {import_id: idx for idx, import_id in enumerate(import_ids)}
    imports.sort(key=lambda doc: order.get(doc["import_id"], len(order)))

    resolved_ids = [doc["import_id"] for doc in imports]
    items = repository.list_items_by_import_ids(resolved_ids, exclude_excluded=False)
    included_item_count = sum(1 for item in items if not item.get("is_excluded"))

    export_batch_id = str(uuid.uuid4())
    exported_at = datetime.now(timezone.utc)
    file_format = file_format.lower()

    if file_format == "csv":
        content = export_excel.build_products_csv(imports, items)
    else:
        content = export_excel.build_workbook(imports, items, exported_at)

    target_path = storage.export_path(export_batch_id, file_format)
    target_path.write_bytes(content)
    relative_path = storage.relative_to_root(target_path)

    export_info = ExportInfoContract(
        export_batch_id=export_batch_id, file_format=file_format.upper(),
        storage_path=relative_path, row_count=included_item_count,
        exported_by=actor, exported_at=exported_at.isoformat(),
    )
    for import_id in resolved_ids:
        repository.insert_export_history(
            export_batch_id, import_id, file_format.upper(), relative_path,
            included_item_count, actor,
        )
        repository.update_import_fields(import_id, {
            "status": "EXPORTED", "is_exported": True,
            "latest_export_json": export_info.model_dump(),
        })

    logger.info(
        "document_extraction.export batch=%s imports=%d format=%s rows=%d",
        export_batch_id, len(resolved_ids), file_format, included_item_count,
    )
    return {"export_batch_id": export_batch_id, "row_count": included_item_count, "file_format": file_format}


def get_export_file(export_batch_id):
    """Returns (content_bytes, filename, media_type) or None. Serves the
    already-generated file from storage — never regenerates it."""
    row = repository.get_export_by_batch(export_batch_id)
    if row is None:
        return None
    extension = row["file_format"].lower()
    media_type = (
        "text/csv" if extension == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    content = storage.absolute_path(row["storage_path"]).read_bytes()
    return content, f"{export_batch_id}.{extension}", media_type


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


_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".tif": "image/tiff", ".tiff": "image/tiff",
}


def _image_media_type(path):
    return _IMAGE_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")


def get_original_file(import_id, page_no=1):
    """(absolute_path, media_type) for one page of the ORIGINAL upload
    (History/Review's "Original Image"), or None if the import/page/file
    doesn't exist on disk. PDFs have no single-page original file to serve
    this way — Review/History fall back to the preview image for those."""
    doc = repository.get_import(import_id)
    if not doc:
        return None
    files = (doc.get("original_files_json") or {}).get("files", [])
    entry = next((f for f in files if f["page_no"] == page_no), None)
    if not entry or not entry.get("storage_path"):
        return None
    path = storage.absolute_path(entry["storage_path"])
    if not path.exists():
        return None
    return path, _image_media_type(path)


def get_preview_file(import_id, page_no=1):
    """(absolute_path, media_type) for one page's Chunk-5-processed preview
    image ("Processed Image"). Falls back to doc_import.preview_image_path
    (the first successfully processed page) when processed_files_json has
    no entry for this exact page — covers the common page_no=1 case even
    before per-page tracking existed."""
    doc = repository.get_import(import_id)
    if not doc:
        return None
    files = (doc.get("processed_files_json") or {}).get("files", [])
    entry = next((f for f in files if f["page_no"] == page_no), None)
    storage_path = entry.get("processed_storage_path") if entry else None
    if not storage_path and page_no == 1:
        storage_path = doc.get("preview_image_path")
    if not storage_path:
        return None
    path = storage.absolute_path(storage_path)
    if not path.exists():
        return None
    return path, _image_media_type(path)


# --------------------------------------------------------------------------
# Corrections (Chunk 15)
# --------------------------------------------------------------------------

def list_corrections(import_id, page=1, page_size=100):
    rows, total = repository.list_corrections(import_id, page, page_size)
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


# --------------------------------------------------------------------------
# Delete / Reprocess (Chunk 13)
# --------------------------------------------------------------------------

def delete_import(import_id, actor):
    return repository.soft_delete_import(import_id, actor)


_REPROCESS_STAGES = ["preprocessing", "ocr", "extraction", "validation"]
_STAGE_RUNNERS = {
    "preprocessing": run_image_processing,
    "ocr": run_ocr,
    "extraction": run_extraction,
    "validation": run_validation,
}


def reprocess(import_id, from_stage, actor):
    """Re-runs the pipeline from `from_stage` onward, in order — e.g.
    from_stage='ocr' re-runs OCR, then extraction, then validation."""
    doc = repository.get_import(import_id)
    if not doc:
        return None
    start_idx = _REPROCESS_STAGES.index(from_stage)
    for stage in _REPROCESS_STAGES[start_idx:]:
        _STAGE_RUNNERS[stage](import_id, actor)
    return repository.get_import(import_id)


# --------------------------------------------------------------------------
# Supplier Lookup (Chunk 14) — the Review UI's manual supplier-assignment
# search box, reusing supplier_engine's own repository rather than the
# GST->DL->Phone->Name priority chain (that chain is for the *automatic*
# pipeline match, which stops at the first hit; a manual search box should
# show every candidate across all provided fields, ranked, for a human to
# pick from).
# --------------------------------------------------------------------------

_LOOKUP_METHOD_CONFIDENCE = {"GST": 95.0, "DL": 90.0, "PHONE": 70.0, "NAME": 50.0}


def lookup_supplier(tenant_id, store_id, gst_number=None, dl_number=None, phone=None, name=None):
    candidates = []
    for method, finder, value in (
        ("GST", supplier_master_repository.find_by_gst, gst_number),
        ("DL", supplier_master_repository.find_by_dl_number, dl_number),
        ("PHONE", supplier_master_repository.find_by_phone, phone),
        ("NAME", supplier_master_repository.search_by_name, name),
    ):
        if not value:
            continue
        for row in finder(tenant_id, store_id, value):
            candidates.append({**row, "match_method": method, "match_confidence": _LOOKUP_METHOD_CONFIDENCE[method]})

    best_by_code = {}
    for candidate in candidates:
        code = candidate["supplier_code"]
        if code not in best_by_code or candidate["match_confidence"] > best_by_code[code]["match_confidence"]:
            best_by_code[code] = candidate
    return sorted(best_by_code.values(), key=lambda c: c["match_confidence"], reverse=True)


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
