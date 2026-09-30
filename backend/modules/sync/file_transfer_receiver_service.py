"""FILE_TRANSFER receiver pipeline (objective 13):

    RECEIVE -> VERIFY CHECKSUM -> VALIDATE MANIFEST -> VALIDATE STORE/TENANT
            -> CHECK DUPLICATE -> STAGE/MERGE -> COMMIT -> ACKNOWLEDGE

Each step's failure mode is distinguished so an operator can tell "this
package was garbage" (REJECTED, permanent) from "this package was fine but
importing it broke" (FAILED, retryable by re-running the tick -- the
package stays in file_sync_packages with status FAILED so it is not
re-registered, but an operator-triggered re-import can retry the merge step
using the already-durable extracted manifest/chunks).
"""
import json
import os
import shutil
import tempfile

from modules.sync import file_transfer_repository as repo
from modules.sync.file_transfer_validator import (
    PackageValidationError, extract_package, verify_checksums, load_manifest,
    load_chunk_bodies, _sha256_file,
)

_last_tick = {"at": None, "summary": None, "error": None}


def get_status():
    return dict(_last_tick)


def run_tick(receiver_transport):
    """One receiver pass across every store's inbox. Never raises -- a
    transport outage (SFTP down, IMAP unreachable) degrades to "this tick
    imported nothing", never to an exception that could kill a scheduler
    thread with no supervisor."""
    import datetime as _dt
    try:
        imported = rejected = failed = 0
        for remote_name, local_zip_path in receiver_transport.list_incoming():
            outcome = _import_one(receiver_transport, remote_name, local_zip_path)
            if outcome == "IMPORTED":
                imported += 1
            elif outcome == "REJECTED":
                rejected += 1
            elif outcome == "FAILED":
                failed += 1
            # DUPLICATE is intentionally not counted as an error -- routine
            # idempotent no-op, e.g. a re-picked-up file after a crash.
        summary = {"imported": imported, "rejected": rejected, "failed": failed}
        _last_tick.update(at=_dt.datetime.now(), summary=summary, error=None)
        return summary
    except Exception as ex:
        _last_tick.update(at=_dt.datetime.now(), error=str(ex))
        return {"ran": False, "error": str(ex)}


def _import_one(receiver_transport, remote_name, local_zip_path):
    try:
        checksum = _sha256_file(local_zip_path)

        # Idempotency pre-check (objective 14): same checksum already
        # processed -> archive and move on, never re-import.
        existing = repo.find_by_checksum(checksum)
        if existing:
            receiver_transport.archive_incoming(remote_name, success=True)
            return "DUPLICATE"

        extract_dir = None
        try:
            extract_dir = extract_package(local_zip_path)
            verify_checksums(extract_dir)
            manifest = load_manifest(extract_dir)

            existing = repo.find_by_id(manifest["package_id"])
            if existing:
                receiver_transport.archive_incoming(remote_name, success=True)
                return "DUPLICATE"

            store_id = manifest.get("store_id")
            if not store_id or not repo.store_exists(store_id):
                raise PackageValidationError("Unknown or missing store_id: %r" % store_id)
            if not manifest.get("tenant_id"):
                manifest["tenant_id"] = repo.resolve_tenant_id(store_id)

            chunk_bodies = load_chunk_bodies(extract_dir, manifest)

            source_filename = remote_name.rsplit("/", 1)[-1]
            repo.register_received(manifest, source_filename, checksum, _transport_mode(receiver_transport))
            repo.mark_validated(manifest["package_id"])
        except Exception as ex:
            # PackageValidationError = the package itself is bad (malformed
            # zip, bad checksum, unknown store, ...) -- permanent, REJECTED.
            # Anything else (e.g. a DB blip during register_received, or a
            # rare race against another receiver process for the same
            # checksum) is transient -- FAILED, retried whole next tick since
            # it was never durably registered as RECEIVED.
            status = "REJECTED" if isinstance(ex, PackageValidationError) else "FAILED"
            manifest_ref = manifest if "manifest" in locals() else None
            if manifest_ref and status == "REJECTED":
                try:
                    repo.mark_rejected(manifest_ref["package_id"], str(ex))
                except Exception:
                    pass
            if status == "REJECTED":
                receiver_transport.archive_incoming(remote_name, success=False)
            # FAILED: leave the file in the inbox so the next tick retries it
            # automatically -- it was never durably registered, so retrying
            # means re-running validation from scratch, not resuming a
            # half-imported state.
            _send_result(receiver_transport, manifest_ref, remote_name,
                        status=status, error_message=str(ex))
            return status
        finally:
            if extract_dir:
                shutil.rmtree(extract_dir, ignore_errors=True)

        try:
            repo.mark_import_started(manifest["package_id"])
            result = repo.import_package(manifest, chunk_bodies)
            repo.mark_imported(manifest["package_id"], result["tables_imported"],
                               result["tables_failed"])
            receiver_transport.archive_incoming(remote_name, success=True)
            _send_result(receiver_transport, manifest, remote_name, status="IMPORTED",
                        result=result)
            return "IMPORTED"
        except Exception as ex:
            repo.mark_failed(manifest["package_id"], str(ex))
            # Not quarantined -- a merge-time failure (e.g. transient DB
            # issue) may succeed on a manual retry against the same package;
            # quarantine is reserved for packages that failed validation.
            receiver_transport.archive_incoming(remote_name, success=False)
            _send_result(receiver_transport, manifest, remote_name, status="FAILED",
                        error_message=str(ex))
            return "FAILED"
    finally:
        try:
            os.remove(local_zip_path)
        except OSError:
            pass


def _transport_mode(receiver_transport):
    return type(receiver_transport).__name__.replace("ReceiverTransport", "").upper() or "UNKNOWN"


def _send_result(receiver_transport, manifest, remote_name, status, error_message=None, result=None):
    """Best-effort ack delivery -- objective 8/9. If this fails, the store's
    package simply stays SENT (not ACKNOWLEDGED) in its own outbox and the
    store will see it as still-in-flight; it will not re-send it (the
    package already left the outbox's pending state), so a lost ack is a
    visibility gap, not a duplicate-import risk (checksum idempotency
    covers that independently)."""
    package_id = (manifest or {}).get("package_id")
    store_id = (manifest or {}).get("store_id") or remote_name.split("/", 1)[0]
    payload = {
        "package_id": package_id,
        "status": status,
        "error_message": error_message,
        "tables_imported": (result or {}).get("tables_imported"),
        "tables_failed": (result or {}).get("tables_failed"),
    }
    tmp = tempfile.NamedTemporaryFile(
        prefix="nexora_result_", suffix=".json", mode="w", delete=False, encoding="utf-8"
    )
    try:
        json.dump(payload, tmp)
        tmp.close()
        result_filename = "%s.json" % (package_id or os.path.basename(remote_name))
        receiver_transport.send_result(store_id, result_filename, tmp.name)
    except Exception:
        pass  # best-effort; see docstring
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass
