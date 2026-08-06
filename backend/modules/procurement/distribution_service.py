"""Internal Supplier Stock Distribution — pipeline + config + logs.

Generates one Excel file per target store from a single source ("HO") store's
own stock — e.g. NMW acting as an internal supplier for NMS/NMC/NMG/NMA — and
writes the results into the SAME procurement.supplier_stock table the
external Supplier Live Stock importer uses (supplier_stock_import.py),
tagged supplier_code = source_store_code, source = 'internal_distribution'.
That keeps every downstream read (GET .../supplier-stock) unchanged: HO shows
up exactly like any other supplier.

Pipeline per run: collect source stock ONCE -> for each enabled target store,
validate -> generate Excel -> replace that store's procurement.supplier_stock
rows for this internal supplier -> queue for WhatsApp (send not wired yet) ->
log. One store's failure never stops the others.
"""

import os
import time
import uuid

from config.database import get_connection
from modules.procurement import supplier_stock_import as ssi
from modules.procurement.distribution_providers import get_provider
from modules.procurement.reports.excel_exporter import ExcelExporter
from modules.procurement._dbutil import as_uid, rows_to_dicts, stringify

_SQL_DIR = os.path.join(os.path.dirname(__file__), "sql")
_DDL_FILES = [
    os.path.join(_SQL_DIR, "0021_supplier_stock_distribution.sql"),
    os.path.join(_SQL_DIR, "0022_store_supplier_map.sql"),
]
_STORAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage", "distribution"
)


def apply_ddl():
    conn = get_connection()
    try:
        cur = conn.cursor()
        for ddl_file in _DDL_FILES:
            with open(ddl_file, "r", encoding="utf-8") as fh:
                script = fh.read()
            for batch in [b.strip() for b in script.split("\nGO") if b.strip()]:
                cur.execute(batch)
        conn.commit()
    finally:
        conn.close()


def _stores(conn, tenant_id):
    cur = conn.cursor()
    cur.execute(
        "SELECT store_id, store_code, store_name FROM dbo.stores WHERE tenant_id = ?",
        (tenant_id,),
    )
    return rows_to_dicts(cur)


# --------------------------------------------------------------------------
# Config (which stores receive the feed + where to notify)
# --------------------------------------------------------------------------

def list_config(tenant_id, source_store_code="NMW"):
    apply_ddl()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT s.store_id, s.store_code, s.store_name,
                   c.whatsapp_group, c.phone_number,
                   COALESCE(c.enabled, 1) AS enabled,
                   m.local_supplier_code
            FROM dbo.stores s
            LEFT JOIN procurement.distribution_config c
                ON c.tenant_id = s.tenant_id AND c.store_id = s.store_id
            LEFT JOIN procurement.store_supplier_map m
                ON m.tenant_id = s.tenant_id AND m.store_id = s.store_id
               AND m.source_store_code = ?
            WHERE s.tenant_id = ?
            ORDER BY s.store_code
            """,
            (source_store_code, tenant_id),
        )
        return [stringify(r) for r in rows_to_dicts(cur)]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Store supplier code mapping -- what a target store's OWN order/purchase
# screens call the source store as a supplier (mirrors legacy Ho_code:
# NMS/NMA='94', NMC='ST_2', NMG='99'). Falls back to the source store code
# itself when a store has no mapping row.
# --------------------------------------------------------------------------

def local_supplier_code(conn, tenant_id, store_id, source_store_code):
    cur = conn.cursor()
    cur.execute(
        "SELECT local_supplier_code FROM procurement.store_supplier_map "
        "WHERE tenant_id = ? AND store_id = ? AND source_store_code = ?",
        (tenant_id, store_id, source_store_code),
    )
    row = cur.fetchone()
    return row[0] if row else source_store_code


def import_legacy_supplier_map(tenant_id, source_store_code="NMW"):
    """One-shot: copy dbo.Stores.Ho_code from the legacy OrderNMC database
    into procurement.store_supplier_map, keyed by store_code. Stores with no
    Ho_code set (or that don't exist in this tenant) are skipped."""
    from modules.legacy_order import repository as legacy_repo

    legacy_stores = {
        s["store_name"]: s["ho_code"]
        for s in legacy_repo.list_stores(active_only=False)
        if s["ho_code"] and s["store_name"] != source_store_code
    }
    conn = get_connection()
    try:
        stores = {s["store_code"]: s["store_id"] for s in _stores(conn, tenant_id)}
    finally:
        conn.close()

    imported, skipped = [], []
    for store_code, ho_code in legacy_stores.items():
        store_id = stores.get(store_code)
        if not store_id:
            skipped.append(store_code)
            continue
        save_supplier_map(tenant_id, store_id, source_store_code, ho_code)
        imported.append({"store_code": store_code, "local_supplier_code": ho_code})
    return {"imported": imported, "skipped": skipped}


def save_supplier_map(tenant_id, store_id, source_store_code, local_code):
    apply_ddl()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT store_supplier_map_id FROM procurement.store_supplier_map "
            "WHERE tenant_id = ? AND store_id = ? AND source_store_code = ?",
            (tenant_id, store_id, source_store_code),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE procurement.store_supplier_map SET local_supplier_code = ?, "
                "updated_at = GETDATE() WHERE store_supplier_map_id = ?",
                (local_code, row[0]),
            )
        else:
            cur.execute(
                "INSERT INTO procurement.store_supplier_map "
                "(tenant_id, store_id, source_store_code, local_supplier_code) "
                "VALUES (?, ?, ?, ?)",
                (tenant_id, store_id, source_store_code, local_code),
            )
        conn.commit()
        return {"saved": True}
    finally:
        conn.close()


def save_config(tenant_id, store_id, whatsapp_group, phone_number, enabled):
    apply_ddl()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT distribution_config_id FROM procurement.distribution_config "
            "WHERE tenant_id = ? AND store_id = ?",
            (tenant_id, store_id),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE procurement.distribution_config SET whatsapp_group = ?, "
                "phone_number = ?, enabled = ?, updated_at = GETDATE() "
                "WHERE distribution_config_id = ?",
                (whatsapp_group, phone_number, 1 if enabled else 0, row[0]),
            )
        else:
            cur.execute(
                "INSERT INTO procurement.distribution_config "
                "(tenant_id, store_id, store_code, whatsapp_group, phone_number, enabled) "
                "SELECT ?, ?, store_code, ?, ?, ? FROM dbo.stores WHERE store_id = ?",
                (tenant_id, store_id, whatsapp_group, phone_number, 1 if enabled else 0, store_id),
            )
        conn.commit()
        return {"saved": True}
    finally:
        conn.close()


# --------------------------------------------------------------------------
# Generation pipeline
# --------------------------------------------------------------------------

def _target_stores(conn, tenant_id, source_store_code, only_store_ids=None):
    stores = _stores(conn, tenant_id)
    targets = [s for s in stores if s["store_code"] != source_store_code]
    if only_store_ids:
        wanted = {str(i) for i in only_store_ids}
        targets = [s for s in targets if str(s["store_id"]) in wanted]
    cur = conn.cursor()
    cur.execute(
        "SELECT store_id, enabled FROM procurement.distribution_config WHERE tenant_id = ?",
        (tenant_id,),
    )
    enabled_map = {str(r[0]): bool(r[1]) for r in cur.fetchall()}
    return [t for t in targets if enabled_map.get(str(t["store_id"]), True)]


def _build_workbook(rows, store_code):
    sheet_rows = [
        {
            "ProductCode": r["code"],
            "ProductName": r["name"],
            "Stock": r["stock"],
            "DiscPercent": r["disc_percent"],
        }
        for r in rows
    ]
    return ExcelExporter.build_workbook(sheet_rows, f"SupplierStock_{store_code}")


def _replace_supplier_stock(conn, tenant_id, target_store_id, supplier_code, rows):
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM procurement.supplier_stock "
        "WHERE tenant_id = ? AND store_id = ? AND supplier_code = ? AND source = 'internal_distribution'",
        (tenant_id, target_store_id, supplier_code),
    )
    stock_rows = [(
        tenant_id, target_store_id, supplier_code, r["code"], r["name"],
        None, r["stock"], None, None, r["disc_percent"], None, None, None,
        None, None, "internal_distribution", 1, None,
    ) for r in rows]
    inserted = ssi.insert_stock_rows(conn, stock_rows)
    ssi.resolve_product_codes(conn, tenant_id, target_store_id, supplier_code)
    return inserted


def _queue_whatsapp(conn, run_item_id, tenant_id, target_store_id, excel_path):
    cur = conn.cursor()
    cur.execute(
        "SELECT whatsapp_group, phone_number, enabled FROM procurement.distribution_config "
        "WHERE tenant_id = ? AND store_id = ?",
        (tenant_id, target_store_id),
    )
    row = cur.fetchone()
    if not row or not row[2]:
        return "not_queued"
    cur.execute(
        "INSERT INTO procurement.distribution_queue "
        "(run_item_id, tenant_id, store_id, whatsapp_group, phone_number, excel_path, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'queued')",
        (run_item_id, tenant_id, target_store_id, row[0], row[1], excel_path),
    )
    return "queued"


def generate(tenant_id, source_store_code, provider_name, only_store_ids=None,
             started_by=None, excel_only=False, supplier_update_only=False):
    """Run the full distribution pipeline. ``excel_only`` skips the
    supplier_stock write; ``supplier_update_only`` skips writing the Excel
    file to disk (still generated in memory to size the run)."""
    apply_ddl()
    os.makedirs(_STORAGE_DIR, exist_ok=True)
    provider = get_provider(provider_name)

    conn = get_connection()
    try:
        run_id = str(uuid.uuid4())
        targets = _target_stores(conn, tenant_id, source_store_code, only_store_ids)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO procurement.distribution_run "
            "(run_id, tenant_id, source_store_code, provider, stores_total, started_by) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, tenant_id, source_store_code, provider_name, len(targets), as_uid(started_by)),
        )
        conn.commit()

        try:
            source_rows = provider.fetch_stock(source_store_code)
        except Exception as exc:
            cur.execute(
                "UPDATE procurement.distribution_run SET status = 'failed', "
                "finished_at = GETDATE() WHERE run_id = ?",
                (run_id,),
            )
            conn.commit()
            return {"run_id": run_id, "error": f"Could not read source stock: {exc}", "items": []}

        succeeded, failed, items = 0, 0, []
        for store in targets:
            t0 = time.time()
            run_item_id = str(uuid.uuid4())
            cur.execute(
                "INSERT INTO procurement.distribution_run_item "
                "(run_item_id, run_id, tenant_id, store_id, store_code) VALUES (?, ?, ?, ?, ?)",
                (run_item_id, run_id, tenant_id, store["store_id"], store["store_code"]),
            )
            conn.commit()
            try:
                excel_path = None
                if not supplier_update_only:
                    content = _build_workbook(source_rows, store["store_code"])
                    excel_path = os.path.join(_STORAGE_DIR, f"SupplierStock_{store['store_code']}.xlsx")
                    with open(excel_path, "wb") as fh:
                        fh.write(content)

                imported = 0
                if not excel_only:
                    # Filed under THIS store's own code for the source supplier
                    # (procurement.store_supplier_map), not the literal source
                    # store code -- NMS/NMA file NMW as '94', NMC as 'ST_2', etc.
                    supplier_code = local_supplier_code(conn, tenant_id, store["store_id"], source_store_code)
                    imported = _replace_supplier_stock(
                        conn, tenant_id, store["store_id"], supplier_code, source_rows
                    )
                    conn.commit()

                wa_status = "not_queued"
                if excel_path and not supplier_update_only:
                    wa_status = _queue_whatsapp(conn, run_item_id, tenant_id, store["store_id"], excel_path)
                    conn.commit()

                duration_ms = int((time.time() - t0) * 1000)
                cur.execute(
                    "UPDATE procurement.distribution_run_item SET finished_at = GETDATE(), "
                    "duration_ms = ?, rows_exported = ?, rows_imported = ?, excel_path = ?, "
                    "supplier_updated = ?, whatsapp_status = ?, status = 'success' "
                    "WHERE run_item_id = ?",
                    (duration_ms, len(source_rows), imported, excel_path,
                     0 if excel_only else 1, wa_status, run_item_id),
                )
                conn.commit()
                succeeded += 1
                items.append({"store_code": store["store_code"], "status": "success",
                              "rows": len(source_rows), "whatsapp_status": wa_status})
            except Exception as exc:
                conn.rollback()
                duration_ms = int((time.time() - t0) * 1000)
                cur.execute(
                    "UPDATE procurement.distribution_run_item SET finished_at = GETDATE(), "
                    "duration_ms = ?, status = 'failed', error_message = ? WHERE run_item_id = ?",
                    (duration_ms, str(exc)[:1000], run_item_id),
                )
                conn.commit()
                failed += 1
                items.append({"store_code": store["store_code"], "status": "failed", "error": str(exc)})

        cur.execute(
            "UPDATE procurement.distribution_run SET status = 'completed', finished_at = GETDATE(), "
            "stores_succeeded = ?, stores_failed = ? WHERE run_id = ?",
            (succeeded, failed, run_id),
        )
        conn.commit()
        return {"run_id": run_id, "stores_total": len(targets),
                "stores_succeeded": succeeded, "stores_failed": failed, "items": items}
    finally:
        conn.close()


def list_runs(tenant_id, limit=20):
    apply_ddl()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT TOP ({int(limit)}) run_id, source_store_code, provider, started_at, finished_at,
                   status, stores_total, stores_succeeded, stores_failed
            FROM procurement.distribution_run
            WHERE tenant_id = ?
            ORDER BY started_at DESC
            """,
            (tenant_id,),
        )
        return [stringify(r) for r in rows_to_dicts(cur)]
    finally:
        conn.close()


def run_detail(run_id):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM procurement.distribution_run WHERE run_id = ?",
            (run_id,),
        )
        run = rows_to_dicts(cur)
        cur.execute(
            "SELECT * FROM procurement.distribution_run_item WHERE run_id = ? ORDER BY store_code",
            (run_id,),
        )
        items = rows_to_dicts(cur)
        return {
            "run": stringify(run[0]) if run else None,
            "items": [stringify(i) for i in items],
        }
    finally:
        conn.close()


def retry_failed(run_id, provider_name=None, started_by=None):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tenant_id, source_store_code, provider FROM procurement.distribution_run WHERE run_id = ?",
            (run_id,),
        )
        run = cur.fetchone()
        if not run:
            raise ValueError("Run not found")
        tenant_id, source_store_code, provider = run
        cur.execute(
            "SELECT store_id FROM procurement.distribution_run_item WHERE run_id = ? AND status = 'failed'",
            (run_id,),
        )
        failed_store_ids = [str(r[0]) for r in cur.fetchall()]
        if not failed_store_ids:
            return {"run_id": run_id, "items": [], "stores_total": 0, "stores_succeeded": 0, "stores_failed": 0}
        return generate(
            str(tenant_id), source_store_code, provider_name or provider,
            only_store_ids=failed_store_ids, started_by=started_by,
        )
    finally:
        conn.close()
