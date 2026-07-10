"""Frozen JSON contracts for every JSON column on dbo.doc_import.

These are the ONLY shapes allowed to be stored in original_files_json,
processed_files_json, ocr_json, validation_json, and latest_export_json (plus
the SupplierMatch API-response shape, which is composed from flat columns,
not stored as JSON — see SupplierMatchContract's docstring). Human-readable
mirror: docs/Document_Extraction_JSON_Contracts.md — keep both in sync.

Future code MUST reuse these models rather than inventing a new ad hoc dict
shape for the same concept. If a stage needs a field that doesn't exist here,
extend the model (and the doc), don't bypass it.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel

PageProcessingStatus = Literal["PENDING", "PROCESSING", "DONE", "FAILED"]
ValidationSeverity = Literal["ERROR", "WARNING"]
SupplierMatchMethod = Literal["GST", "DL", "PHONE", "NAME", "MANUAL", "UNKNOWN"]
ExportFileFormat = Literal["XLSX", "CSV"]


# --------------------------------------------------------------------------
# OriginalFiles — doc_import.original_files_json
# --------------------------------------------------------------------------

class OriginalFileEntry(BaseModel):
    page_no: int
    original_file_name: str
    storage_path: str
    display_order: int
    rotation: int = 0
    processing_status: PageProcessingStatus = "PENDING"


class OriginalFilesContract(BaseModel):
    files: List[OriginalFileEntry]


# --------------------------------------------------------------------------
# ProcessedFiles — doc_import.processed_files_json (Chunk 5 populates this)
# --------------------------------------------------------------------------

class ProcessedFileEntry(BaseModel):
    page_no: int
    processed_storage_path: Optional[str] = None  # None when processing_status = "FAILED"
    rotation_degrees: int = 0
    deskew_angle: Optional[float] = None
    width_px: Optional[int] = None
    height_px: Optional[int] = None
    processing_status: PageProcessingStatus = "PENDING"
    processing_notes: Optional[str] = None


class ProcessedFilesContract(BaseModel):
    files: List[ProcessedFileEntry]


# --------------------------------------------------------------------------
# OCRResult — doc_import.ocr_json (the NORMALIZED model — see § OCR output
# contract in the Design doc. Raw PaddleOCR output is transformed into this
# shape before it ever reaches storage or extraction logic.)
# --------------------------------------------------------------------------

class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class OCRWord(BaseModel):
    text: str
    confidence: float
    bbox: BBox


class OCRLine(BaseModel):
    line_no: int
    text: str
    confidence: float
    bbox: BBox
    words: List[OCRWord] = []


class OCRPage(BaseModel):
    page_no: int
    lines: List[OCRLine] = []


class OCRResultContract(BaseModel):
    engine_name: str = "PaddleOCR"
    engine_version: Optional[str] = None
    pages: List[OCRPage]
    average_confidence: Optional[float] = None


# --------------------------------------------------------------------------
# SupplierMatch — API response shape only. Composed on read from doc_import's
# flat supplier_* columns (gst_number, matched_supplier_code, ...), NOT
# stored as its own JSON blob — those columns are indexed (IX_doc_import_
# supplier_code, IX_doc_import_gst_invoice_dup) for the GST/DL/duplicate
# lookups, and folding them into JSON would make that indexing impossible.
# This model documents the contract callers can rely on; service.py's
# get_extraction() is the one place that assembles it.
# --------------------------------------------------------------------------

class SupplierMatchContract(BaseModel):
    ocr_supplier_name: Optional[str] = None
    matched_supplier_name: Optional[str] = None
    matched_supplier_code: Optional[str] = None
    gst_number: Optional[str] = None
    dl_number: Optional[str] = None
    supplier_phone: Optional[str] = None
    supplier_address: Optional[str] = None
    match_method: Optional[SupplierMatchMethod] = None
    match_confidence: Optional[float] = None
    is_unknown: bool = False


# --------------------------------------------------------------------------
# Validation — doc_import.validation_json (a bare JSON array, not wrapped in
# an object — matches what repository.py already reads/writes)
# --------------------------------------------------------------------------

class ValidationFinding(BaseModel):
    rule_code: str
    severity: ValidationSeverity
    field: Optional[str] = None
    item_id: Optional[int] = None
    message: str
    expected_value: Optional[str] = None
    actual_value: Optional[str] = None


ValidationContract = List[ValidationFinding]


# --------------------------------------------------------------------------
# ExportInfo — doc_import.latest_export_json
# --------------------------------------------------------------------------

class ExportInfoContract(BaseModel):
    export_batch_id: str
    file_format: ExportFileFormat
    storage_path: Optional[str] = None
    row_count: Optional[int] = None
    exported_by: Optional[str] = None
    exported_at: str  # ISO-8601 timestamp
