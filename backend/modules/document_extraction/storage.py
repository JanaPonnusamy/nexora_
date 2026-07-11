"""Local disk storage for uploaded invoices, previews, and exports.

Layout (see docs/Document_Extraction_Design.md § File storage):
    data/document_extraction/{import_id}/original/...
    data/document_extraction/{import_id}/preview/...
    data/document_extraction/{import_id}/export/{export_batch_id}.xlsx

No blob-storage dependency — matches the platform's existing local-disk
convention for generated artifacts. Root is configurable via
DOCUMENT_EXTRACTION_DATA_DIR for deployments that want it elsewhere.
"""

import hashlib
import os
from pathlib import Path

_EXTENSION_TO_SOURCE_TYPE = {
    ".pdf": "PDF",
    ".jpg": "JPG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".tif": "TIFF",
    ".tiff": "TIFF",
}

ALLOWED_EXTENSIONS = tuple(_EXTENSION_TO_SOURCE_TYPE)


def _data_root() -> Path:
    override = os.getenv("DOCUMENT_EXTRACTION_DATA_DIR")
    if override:
        return Path(override)
    # backend/modules/document_extraction/storage.py -> repo root is 3 levels up
    return Path(__file__).resolve().parents[3] / "data" / "document_extraction"


def source_type_for_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    source_type = _EXTENSION_TO_SOURCE_TYPE.get(ext)
    if not source_type:
        raise ValueError(f"Unsupported file type: {filename}")
    return source_type


def compute_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def compute_combined_checksum(contents) -> str:
    """Order-preserving checksum across every file in a multi-file (one
    invoice, multiple pages) upload. Hashing only the first file here would
    make duplicate detection blind to differences in page 2+ — this hashes
    the sequence of per-file digests instead."""
    hasher = hashlib.sha256()
    for content in contents:
        hasher.update(compute_checksum(content).encode("ascii"))
    return hasher.hexdigest()


def _import_dir(import_id, subfolder: str) -> Path:
    path = _data_root() / str(import_id) / subfolder
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_original(import_id, filename: str, content: bytes) -> str:
    """Writes an uploaded file to the import's original/ folder and returns
    a path relative to the storage root (what gets stored in
    doc_import.original_file_path)."""
    directory = _import_dir(import_id, "original")
    safe_name = Path(filename).name  # strip any path components from the client
    target = directory / safe_name
    target.write_bytes(content)
    return str(target.relative_to(_data_root())).replace("\\", "/")


def save_preview(import_id, page_no: int, content: bytes, extension: str = "jpg") -> str:
    """Writes a Chunk-5-processed page image to the import's preview/ folder
    and returns a path relative to the storage root (one entry in
    processed_files_json)."""
    directory = _import_dir(import_id, "preview")
    target = directory / f"page_{page_no}.{extension}"
    target.write_bytes(content)
    return str(target.relative_to(_data_root())).replace("\\", "/")


def copy_into_import(source_relative_path: str, dest_import_id, subfolder: str) -> str:
    """Copies an already-stored file (by its storage-root-relative path)
    into a DIFFERENT import's own folder, preserving its filename. Used
    when a multi-page upload turns out to bundle more than one invoice
    (see invoice_boundary.py) and has to be split into separate imports
    after the files already live under the original import_id."""
    source = absolute_path(source_relative_path)
    directory = _import_dir(dest_import_id, subfolder)
    target = directory / source.name
    target.write_bytes(source.read_bytes())
    return str(target.relative_to(_data_root())).replace("\\", "/")


def export_path(export_batch_id, extension: str) -> Path:
    directory = _data_root() / "_exports"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{export_batch_id}.{extension}"


def relative_to_root(path: Path) -> str:
    """Mirrors the relative-path convention save_original()/save_preview()
    already return, for callers (export) that get an absolute Path from
    export_path() and need the same storable/relative form."""
    return str(path.relative_to(_data_root())).replace("\\", "/")


def absolute_path(relative_path: str) -> Path:
    return _data_root() / relative_path
