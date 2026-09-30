"""FILE_TRANSFER package validation: safe extraction, checksum verification,
manifest schema checks. Nothing here trusts the package contents until every
check has passed -- objective 17 (never extract path-traversal entries, never
execute anything from a package, never trust manifest values unvalidated).
"""
import hashlib
import json
import os
import tempfile
import zipfile

MAX_PACKAGE_BYTES = 200 * 1024 * 1024   # 200 MB: a 30-min delta batch, generously bounded
MAX_MEMBER_BYTES = 100 * 1024 * 1024    # single payload/manifest file guard
REQUIRED_MANIFEST_KEYS = (
    "package_id", "execution_id", "schema_version", "store_id",
    "created_at", "sync_mode", "tables", "payload_files", "totals",
)


class PackageValidationError(RuntimeError):
    pass


def _safe_member_path(extract_dir, member_name):
    """Rejects any archive entry that would escape extract_dir (objective 17:
    ../.. traversal, absolute paths, drive-letter paths)."""
    if os.path.isabs(member_name) or ":" in member_name:
        raise PackageValidationError("Unsafe archive entry (absolute path): %r" % member_name)
    dest = os.path.normpath(os.path.join(extract_dir, member_name))
    if not dest.startswith(os.path.normpath(extract_dir) + os.sep) and dest != os.path.normpath(extract_dir):
        raise PackageValidationError("Unsafe archive entry (path traversal): %r" % member_name)
    return dest


def extract_package(zip_path):
    """Extracts a package into a fresh temp dir with path-traversal and
    size guards. Returns the extraction dir (caller must clean it up)."""
    size = os.path.getsize(zip_path)
    if size > MAX_PACKAGE_BYTES:
        raise PackageValidationError(
            "Package exceeds max size (%d > %d bytes)" % (size, MAX_PACKAGE_BYTES)
        )

    extract_dir = tempfile.mkdtemp(prefix="nexora_pkg_import_")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.file_size > MAX_MEMBER_BYTES:
                    raise PackageValidationError(
                        "Archive member too large: %r (%d bytes)"
                        % (info.filename, info.file_size)
                    )
                dest = _safe_member_path(extract_dir, info.filename)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(info, "r") as src, open(dest, "wb") as out:
                    out.write(src.read())
        return extract_dir
    except zipfile.BadZipFile as ex:
        raise PackageValidationError("Corrupt zip archive: %s" % ex) from ex


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_checksums(extract_dir):
    """checksums.json must list every other file with a matching sha256.
    Any mismatch or missing entry fails the whole package -- a package is
    all-or-nothing at the integrity level, even though import itself is
    per-table isolated."""
    checksums_path = os.path.join(extract_dir, "checksums.json")
    if not os.path.isfile(checksums_path):
        raise PackageValidationError("Missing checksums.json")
    with open(checksums_path, "r", encoding="utf-8") as fh:
        checksums = json.load(fh)

    for rel_path, expected in checksums.items():
        full_path = os.path.join(extract_dir, rel_path)
        if not os.path.isfile(full_path):
            raise PackageValidationError("checksums.json references missing file: %r" % rel_path)
        actual = _sha256_file(full_path)
        if actual != expected:
            raise PackageValidationError(
                "Checksum mismatch for %r (package corrupted or tampered in transit)"
                % rel_path
            )


def load_manifest(extract_dir):
    manifest_path = os.path.join(extract_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        raise PackageValidationError("Missing manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    missing = [k for k in REQUIRED_MANIFEST_KEYS if k not in manifest]
    if missing:
        raise PackageValidationError("manifest.json missing required keys: %s" % missing)
    if manifest.get("sync_mode") != "FILE_TRANSFER":
        raise PackageValidationError(
            "manifest.json sync_mode must be 'FILE_TRANSFER', got %r" % manifest.get("sync_mode")
        )

    for rel_path in manifest.get("payload_files") or []:
        if not os.path.isfile(os.path.join(extract_dir, rel_path)):
            raise PackageValidationError("manifest.json references missing payload file: %r" % rel_path)

    return manifest


def load_chunk_bodies(extract_dir, manifest):
    bodies = []
    for rel_path in manifest.get("payload_files") or []:
        with open(os.path.join(extract_dir, rel_path), "r", encoding="utf-8") as fh:
            body = json.load(fh)
        for key in ("execution_id", "table_name", "chunk_no", "rows"):
            if key not in body:
                raise PackageValidationError(
                    "%r is missing required key %r" % (rel_path, key)
                )
        if body["execution_id"] != manifest["execution_id"]:
            raise PackageValidationError(
                "%r execution_id does not match manifest (%r != %r)"
                % (rel_path, body["execution_id"], manifest["execution_id"])
            )
        bodies.append(body)
    return bodies
