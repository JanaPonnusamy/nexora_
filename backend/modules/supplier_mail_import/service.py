"""Supplier mail import: poll a tenant mailbox and import supplier stock files.

Per switched-on supplier, each poll:
  1. finds that supplier's mails (exact sender match) from the last
     lookback_days, newest first;
  2. walks them newest -> oldest, skipping mails already logged as done; a
     mail with no Excel attachment is logged NO_ATTACHMENT and the walk goes on;
  3. imports the first Excel attachment of the newest usable mail through
     the manual import path (excel_import.import_file -- REPLACES the
     supplier's stock for the store; with all_stores, import_file_bulk into
     EVERY active store of the tenant carrying the same supplier code) with
     the supplier's SAVED column mapping only. No saved mapping, or the file no longer has the mapped
     columns -> NEEDS_MAPPING (retried every poll; do one manual import of
     that file to save the mapping);
  4. after a successful import, older unimported mails are logged SUPERSEDED
     so a stale file can never overwrite a newer one.
"""
import logging
import os
import threading
import traceback

from modules.legacy_order import database as legacy_database
from modules.supplier_mail_import import repository
from modules.supplier_mail_import.mailbox import Mailbox, split_addresses, valid_address_list
from modules.supplier_stock_analysis import excel_import

logger = logging.getLogger("supplier_mail_import")

TICK_SECONDS = int(os.getenv("SUPPLIER_MAIL_IMPORT_TICK_SECONDS", "60"))
LOOP_ENABLED = os.getenv("SUPPLIER_MAIL_IMPORT_LOOP", "1") != "0"
IMPORTED_BY = "mail-import"

_stop_event = threading.Event()
_thread = None
_tenant_locks = {}
_locks_guard = threading.Lock()


def _tenant_lock(tenant_id):
    with _locks_guard:
        return _tenant_locks.setdefault(str(tenant_id).upper(), threading.Lock())


# --- configuration ------------------------------------------------------------

def get_config(tenant_id):
    return repository.get_config(tenant_id) or {
        "enabled": False, "imap_host": "", "imap_port": 993, "use_ssl": True, "username": "",
        "has_password": False, "folder": "INBOX", "poll_minutes": 15, "lookback_days": 2,
        "last_poll_at": None, "last_poll_status": None, "last_poll_message": None,
    }


def save_config(tenant_id, payload, actor=None):
    values = {
        "enabled": bool(payload.get("enabled")),
        "imap_host": str(payload.get("imap_host") or "").strip(),
        "imap_port": int(payload.get("imap_port") or 993),
        "use_ssl": bool(payload.get("use_ssl", True)),
        "username": str(payload.get("username") or "").strip(),
        "folder": str(payload.get("folder") or "").strip() or "INBOX",
        "poll_minutes": min(max(int(payload.get("poll_minutes") or 15), 5), 1440),
        "lookback_days": min(max(int(payload.get("lookback_days") or 2), 1), 30),
    }
    password = payload.get("password") or None
    if values["enabled"]:
        if not values["imap_host"] or not values["username"]:
            raise ValueError("Mail server and username are required to switch mail import on.")
        if not password and not (repository.get_config(tenant_id) or {}).get("has_password"):
            raise ValueError("Enter the mailbox password to switch mail import on.")
    repository.save_config(tenant_id, values, password, actor)
    return get_config(tenant_id)


def test_connection(tenant_id, payload=None):
    """Sign in with the given (unsaved) settings, or the saved ones; a blank
    password uses the saved one."""
    saved = repository.get_config(tenant_id, with_password=True) or {}
    config = {**saved, **{k: v for k, v in (payload or {}).items() if v not in (None, "")}}
    if not config.get("imap_host") or not config.get("username") or not config.get("password"):
        raise ValueError("Mail server, username and password are required.")
    try:
        with Mailbox(config) as box:
            return {"ok": True, "message": f"Signed in. {box.message_count} mail(s) in '{config.get('folder') or 'INBOX'}'."}
    except Exception as ex:
        return {"ok": False, "message": _friendly_error(ex)}


def list_suppliers(tenant_id, store_id, store_code):
    rows = repository.list_suppliers(tenant_id, store_id)
    token = legacy_database.set_active_tenant(tenant_id)
    try:
        mapped = repository.mapped_supplier_codes(store_code)
    except Exception:
        mapped = None  # legacy DB unreachable: unknown, not "no mapping"
    finally:
        legacy_database.reset_active_tenant(token)
    latest = repository.latest_by_supplier(tenant_id, store_code)
    for row in rows:
        code = str(row["supplier_code"]).strip()
        row["supplier_code"] = code
        row["has_mapping"] = None if mapped is None else code in mapped
        row["last"] = latest.get(code)
    return rows


def save_supplier(tenant_id, store_id, supplier_code, enabled, mail_from, subject_filter, all_stores=False, actor=None):
    code = str(supplier_code or "").strip()
    mail_from = str(mail_from or "").strip()
    subject_filter = str(subject_filter or "").strip()
    if not code or not repository.supplier_exists(tenant_id, store_id, code):
        raise LookupError("That supplier is not in this store's list.")
    if len(mail_from) > 500 or not valid_address_list(mail_from):
        raise ValueError("Enter valid mail address(es), separated by commas.")
    if len(subject_filter) > 200:
        raise ValueError("Subject filter is too long.")
    if enabled and not mail_from:
        master = next((r for r in repository.list_suppliers(tenant_id, store_id)
                       if str(r["supplier_code"]).strip() == code), {})
        if not split_addresses(master.get("master_email")):
            raise ValueError("This supplier has no mail id in the supplier master - enter one to switch mail import on.")
    repository.save_supplier(tenant_id, store_id, code, enabled, mail_from, subject_filter, all_stores, actor)


# --- polling --------------------------------------------------------------------

def run_tenant(tenant_id):
    """Poll the tenant mailbox once for every switched-on supplier. Returns
    a summary; never raises (failures are recorded on the config row)."""
    lock = _tenant_lock(tenant_id)
    if not lock.acquire(blocking=False):
        return {"ok": False, "message": "A mail check for this tenant is already running."}
    token = legacy_database.set_active_tenant(tenant_id)
    try:
        config = repository.get_config(tenant_id, with_password=True)
        if not config or not config["imap_host"] or not config["password"]:
            return {"ok": False, "message": "Mailbox is not configured."}
        suppliers = repository.enabled_suppliers(tenant_id)
        if not suppliers:
            repository.record_poll(tenant_id, "OK", "No suppliers are switched on for mail import.")
            return {"ok": True, "message": "No suppliers are switched on for mail import.", "suppliers": []}

        results = []
        with Mailbox(config) as box:
            for supplier in suppliers:
                try:
                    results.append(_run_supplier(box, tenant_id, supplier, config["lookback_days"]))
                except Exception as ex:
                    logger.exception("mail import failed for %s/%s", supplier["store_code"], supplier["supplier_code"])
                    results.append({**_who(supplier), "status": "FAILED", "message": _friendly_error(ex)})

        imported = [r for r in results if r["status"] == "IMPORTED"]
        problems = [r for r in results if r["status"] in ("FAILED", "NEEDS_MAPPING")]
        message = f"{len(imported)} supplier file(s) imported"
        if problems:
            message += "; needs attention: " + ", ".join(f"{r['supplier_name'] or r['supplier_code']} ({r['status']})" for r in problems)
        repository.record_poll(tenant_id, "WARN" if problems else "OK", message)
        return {"ok": True, "message": message, "suppliers": results}
    except Exception as ex:
        message = _friendly_error(ex)
        logger.warning("mail import poll failed for tenant %s: %s", tenant_id, message)
        try:
            repository.record_poll(tenant_id, "FAILED", message)
        except Exception:
            logger.exception("could not record mail poll failure")
        return {"ok": False, "message": message}
    finally:
        legacy_database.reset_active_tenant(token)
        lock.release()


def _who(supplier):
    return {
        "store_code": supplier["store_code"],
        "supplier_code": supplier["supplier_code"],
        "supplier_name": supplier.get("supplier_name") or "",
    }


def _run_supplier(box, tenant_id, supplier, lookback_days):
    who = _who(supplier)
    addresses = split_addresses(supplier.get("mail_from"))
    if not addresses:
        return {**who, "status": "SKIPPED", "message": "No mail id for this supplier."}
    store_code, code = supplier["store_code"], supplier["supplier_code"]

    mails = box.find(addresses, lookback_days, supplier.get("subject_filter") or "")
    if not mails:
        return {**who, "status": "NO_MAIL", "message": "No new mail."}
    keys = {m["message_id"]: repository.dedup_key(tenant_id, store_code, code, m["message_id"]) for m in mails}
    known = repository.statuses(keys.values())

    for index, mail in enumerate(mails):
        key = keys[mail["message_id"]]
        status = known.get(key)
        if status == "IMPORTED":
            return {**who, "status": "UP_TO_DATE", "message": "Latest mail already imported."}
        if status in repository.DONE_STATUSES:
            continue
        if not repository.claim(key, tenant_id, store_code, code, mail):
            return {**who, "status": "BUSY", "message": "Mail is being imported by another worker."}

        attachments = box.excel_attachments(mail["uid"])
        if not attachments:
            repository.finish(key, "NO_ATTACHMENT", "No Excel attachment in this mail.")
            continue

        filename, data = attachments[0]
        result = _import(tenant_id, supplier, data)
        extra = f" ({len(attachments) - 1} more Excel file(s) in the mail ignored)" if len(attachments) > 1 else ""
        if result["status"] != "IMPORTED":
            repository.finish(key, result["status"], result["message"] + extra, filename)
            return {**who, **result, "attachment": filename}
        repository.finish(key, "IMPORTED", result["message"] + extra, filename,
                          result["rows_imported"], result["products_resolved"])
        for older in mails[index + 1:]:
            older_key = keys[older["message_id"]]
            if known.get(older_key) not in repository.DONE_STATUSES:
                repository.supersede(older_key, tenant_id, store_code, code, older)
        return {**who, **result, "attachment": filename}

    return {**who, "status": "NO_MAIL", "message": "No new mail with an Excel file."}


def _import(tenant_id, supplier, data):
    """Import one file with the supplier's saved mapping only -- an import
    REPLACES the supplier's stock, so nothing is guessed."""
    store_id, code = supplier["store_id"], supplier["supplier_code"]
    stores = excel_import.bulk_import_stores(tenant_id, code) if supplier.get("all_stores") else []
    saved = excel_import._saved_mapping(tenant_id, store_id, code)
    # All stores: the mapping may have been saved from any of them.
    for store in stores:
        if saved:
            break
        saved = excel_import._saved_mapping(tenant_id, store["store_id"], code)
    if not saved:
        return {"status": "NEEDS_MAPPING",
                "message": "No saved column mapping for this supplier - import one file manually once to save it."}
    try:
        headers = excel_import.preview(data)["headers"]
    except Exception as ex:
        return {"status": "FAILED", "message": f"Could not read the Excel file: {ex}"}
    mapping = {h: saved[h.lower()] for h in headers if h.lower() in saved}
    mapped = set(mapping.values())
    missing = [t["label"] for t in excel_import.TARGETS if t["mandatory"] and t["value"] not in mapped]
    if missing:
        return {"status": "NEEDS_MAPPING",
                "message": "The file's columns changed - not found: " + ", ".join(missing)
                + ". Import this file manually once to update the mapping."}
    if supplier.get("all_stores"):
        result = excel_import.import_file_bulk(tenant_id, code, data, mapping, None, IMPORTED_BY)
        if not result.get("success"):
            return {"status": "FAILED", "message": result.get("error") or "Import failed."}
        done = result["stores"]
        return {
            "status": "IMPORTED",
            "rows_imported": max((s.get("imported") or 0 for s in done), default=0),
            "products_resolved": sum(s.get("product_codes_resolved") or 0 for s in done),
            "message": f"Imported to {len(done)} store(s): " + ", ".join(
                f"{s['store_code']} {s.get('imported') or 0} ({s.get('product_codes_resolved') or 0} matched)" for s in done),
        }
    result = excel_import.import_file(tenant_id, store_id, code, data, mapping, IMPORTED_BY)
    if not result.get("success"):
        return {"status": "FAILED", "message": result.get("error") or "Import failed."}
    return {
        "status": "IMPORTED",
        "rows_imported": result.get("imported"),
        "products_resolved": result.get("product_codes_resolved"),
        "message": f"Imported {result.get('imported')} product(s); {result.get('product_codes_resolved')} matched.",
    }


def _friendly_error(ex):
    text = str(ex) or ex.__class__.__name__
    if "AUTHENTICATIONFAILED" in text.upper() or "LOGIN" in text.upper() and "FAIL" in text.upper():
        return ("Mailbox sign-in failed. Check the username/password "
                "(Gmail and Outlook need an app password, not the normal password).")
    if isinstance(ex, (TimeoutError, OSError)) and not text.startswith("Mail folder"):
        return f"Could not reach the mail server: {text}"
    return text


# --- background loop ------------------------------------------------------------

def run_due_tenants():
    for tenant_id in repository.due_tenants():
        if _stop_event.is_set():
            return
        run_tenant(tenant_id)


def _loop():
    while not _stop_event.wait(TICK_SECONDS):
        try:
            run_due_tenants()
        except Exception:
            print("[SUPPLIER_MAIL_IMPORT] tick failed:\n" + traceback.format_exc())


def start_background_loop():
    global _thread
    if not LOOP_ENABLED or (_thread and _thread.is_alive()):
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="supplier-mail-import", daemon=True)
    _thread.start()


def run_tenant_in_background(tenant_id):
    threading.Thread(target=run_tenant, args=(tenant_id,), name="supplier-mail-import-now", daemon=True).start()
