"""HO-side tracking for FILE_TRANSFER packages (idempotency ledger + import).

Import itself is delegated entirely to modules.sync.runtime_repository --
the exact staging+MERGE engine DIRECT_HTTP chunk uploads already use
(upload_chunk, report_table_metrics, complete_task/fail_task). This module
only owns two things:
  1. the package envelope (sync.file_sync_packages -- has this exact package
     been seen before, what state is it in), and
  2. creating the dbo.sync_execution row a package's chunks need to exist
     before upload_chunk() can attribute rows to a tenant/store, since a
     FILE_TRANSFER package has no live scheduler tick to have created one.
"""
import json
import os

from config.database import get_connection
from modules.sync import runtime_repository

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")
_DDLS = (os.path.join(_SQL_DIR, "0001_file_sync_packages.sql"),)
_schema_ready = False


def ensure_schema():
    """Self-provisioning migration (same idempotent pattern used across this
    codebase, e.g. modules/procurement/network_movement_repository.py) --
    a fresh environment needs no manual DBA step."""
    global _schema_ready
    if _schema_ready:
        return
    conn = get_connection()
    try:
        cur = conn.cursor()
        for ddl in _DDLS:
            with open(ddl, "r", encoding="utf-8") as fh:
                script = fh.read()
            for batch in (b.strip() for b in script.split("\nGO")):
                if batch:
                    cur.execute(batch)
        conn.commit()
    finally:
        conn.close()
    _schema_ready = True


def find_by_checksum(checksum):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT package_id, status FROM sync.file_sync_packages WHERE checksum = ?",
            (checksum,),
        )
        row = cur.fetchone()
        return {"package_id": str(row[0]), "status": row[1]} if row else None
    finally:
        conn.close()


def find_by_id(package_id):
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT package_id, status FROM sync.file_sync_packages WHERE package_id = ?",
            (package_id,),
        )
        row = cur.fetchone()
        return {"package_id": str(row[0]), "status": row[1]} if row else None
    finally:
        conn.close()


def register_received(manifest, source_filename, checksum, transport_mode):
    """Insert the RECEIVED row. The UNIQUE constraints on package_id
    (primary key) and checksum are the durable idempotency guard: a
    concurrent second receiver process picking up the same physical file
    (or a retried transmission with the same checksum) fails here with a
    constraint violation rather than importing twice. Callers should still
    pre-check find_by_checksum/find_by_id first for a clean DUPLICATE
    response -- this is defense in depth, not the primary path."""
    ensure_schema()
    conn = get_connection()
    try:
        cur = conn.cursor()
        totals = manifest.get("totals") or {}
        cur.execute(
            """
            INSERT INTO sync.file_sync_packages
            (package_id, execution_id, tenant_id, store_id, source_filename,
             checksum, transport_mode, status, schema_version, agent_version,
             total_rows, total_chunks, total_tables, manifest_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'RECEIVED', ?, ?, ?, ?, ?, ?)
            """,
            (manifest["package_id"], manifest.get("execution_id") or manifest["package_id"],
             manifest.get("tenant_id"), manifest.get("store_id"), source_filename,
             checksum, transport_mode, manifest.get("schema_version"),
             manifest.get("agent_version"), totals.get("total_rows"),
             totals.get("total_chunks"), totals.get("total_tables"),
             json.dumps(manifest, default=str)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _update(package_id, **fields):
    if not fields:
        return
    conn = get_connection()
    try:
        cur = conn.cursor()
        sets = ", ".join(k + " = ?" for k in fields)
        cur.execute(
            "UPDATE sync.file_sync_packages SET " + sets + " WHERE package_id = ?",
            (*fields.values(), package_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_rejected(package_id, error_message):
    _update(package_id, status="REJECTED", error_message=error_message)


def mark_validated(package_id):
    _update(package_id, status="VALIDATED")


def mark_import_started(package_id):
    _update(package_id, status="STAGED", import_started_at="__NOW__")
    _stamp_now(package_id, "import_started_at")


def mark_imported(package_id, tables_imported, tables_failed):
    _update(package_id, status="IMPORTED", tables_imported=tables_imported,
           tables_failed=tables_failed)
    _stamp_now(package_id, "import_completed_at")


def mark_failed(package_id, error_message):
    _update(package_id, status="FAILED", error_message=error_message)
    _stamp_now(package_id, "import_completed_at")


def _stamp_now(package_id, column):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE sync.file_sync_packages SET " + column + " = GETDATE() "
            "WHERE package_id = ?",
            (package_id,),
        )
        conn.commit()
    finally:
        conn.close()


def resolve_tenant_id(store_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT tenant_id FROM dbo.stores WHERE store_id = ?", (store_id,))
        row = cur.fetchone()
        return str(row[0]) if row and row[0] else None
    finally:
        conn.close()


def store_exists(store_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM dbo.stores WHERE store_id = ?", (store_id,))
        return cur.fetchone() is not None
    finally:
        conn.close()


def _create_execution_row(execution_id, tenant_id, store_id, manifest):
    conn = get_connection()
    try:
        cur = conn.cursor()
        total_tables = (manifest.get("totals") or {}).get("total_tables", 0)
        cur.execute(
            """
            INSERT INTO dbo.sync_execution
            (execution_id, tenant_id, store_id, execution_type, sync_mode,
             execution_status, total_tables, started_at)
            VALUES (?, ?, ?, 'FILE_TRANSFER', 'FILE_TRANSFER', 'RUNNING', ?, GETDATE())
            """,
            (execution_id, tenant_id, store_id, total_tables),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def import_package(manifest, chunk_bodies):
    """chunk_bodies: list of dicts already loaded from payload/*.json, each
    shaped exactly like a DIRECT_HTTP chunk-upload body (execution_id,
    table_name, chunk_no, rows, total_rows, sync_type).

    Per-table isolation mirrors the agent's run_table_safe: one table's
    staging/merge failure never aborts the rest of the package -- it is
    recorded via report_table_metrics(status='FAILED', ...) and the import
    continues. The whole package is only reported FAILED if every table in
    it failed."""
    execution_id = manifest["execution_id"]
    tenant_id = manifest.get("tenant_id")
    store_id = manifest.get("store_id")
    _create_execution_row(execution_id, tenant_id, store_id, manifest)

    by_table = {}
    for body in chunk_bodies:
        by_table.setdefault(body["table_name"], []).append(body)
    for chunks in by_table.values():
        chunks.sort(key=lambda b: b.get("chunk_no", 0))

    table_summary_by_name = {t["table_name"]: t for t in manifest.get("tables", [])}

    tables_imported = 0
    tables_failed = 0
    for table_name, chunks in by_table.items():
        summary = table_summary_by_name.get(table_name, {})
        try:
            for body in chunks:
                runtime_repository.upload_chunk(
                    body["execution_id"], body["table_name"], body["chunk_no"],
                    body["rows"], total_rows=body.get("total_rows"),
                    sync_type=body.get("sync_type"),
                )
            runtime_repository.report_table_metrics(
                execution_id, table_name, summary.get("sync_mode"),
                summary.get("examined", 0), summary.get("changed", 0),
                summary.get("uploaded", 0), summary.get("skipped", 0),
                summary.get("examined", 0), status="COMPLETED",
            )
            tables_imported += 1
        except Exception as ex:
            tables_failed += 1
            try:
                runtime_repository.report_table_metrics(
                    execution_id, table_name, summary.get("sync_mode"),
                    summary.get("examined", 0), summary.get("changed", 0),
                    0, summary.get("skipped", 0), summary.get("examined", 0),
                    status="FAILED", error_message=str(ex),
                )
            except Exception:
                pass

    # Tables the agent already marked FAILED before packaging (e.g. an
    # extraction error on the store side) never produced any chunks.
    for table_name, summary in table_summary_by_name.items():
        if table_name in by_table:
            continue
        tables_failed += 1
        try:
            runtime_repository.report_table_metrics(
                execution_id, table_name, summary.get("sync_mode"), 0, 0, 0, 0, 0,
                status=summary.get("status", "FAILED"),
                error_message=summary.get("error_message"),
            )
        except Exception:
            pass

    if tables_failed and not tables_imported:
        runtime_repository.fail_task(
            execution_id, "All %d table(s) failed to import" % tables_failed
        )
    else:
        runtime_repository.complete_task(execution_id)

    return {"tables_imported": tables_imported, "tables_failed": tables_failed}
