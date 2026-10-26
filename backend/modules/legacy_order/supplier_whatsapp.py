"""Supplier-wise WhatsApp for the Procurement workspace (store-level WhatsApp).

Each store keeps, per (unified) supplier code, WHERE its orders go on
WhatsApp -- exactly one group, or one or more contacts -- plus the auto-send
rule: once N products are assigned to that supplier and not yet sent, the
Stock Client exports them and posts them from the store's own WhatsApp. The
sent log makes every batch carry only what is new; the "complete" send at
finalize carries the whole order.

Also reads the supplier's recent bills (IV GRNs) and returns (PR, the supplier
answers them with a credit note) for the export footer.
"""
import datetime
import json
import logging
import os
import re

import pyodbc

from modules.legacy_order import database, repository
from modules.legacy_order.order_export import _format_product_code

logger = logging.getLogger(__name__)

SEND_FORMATS = ("image", "excel", "both")
_SCHEMA_READY = False


def _ensure_schema():
    """Apply sql/0011 once per process on its own connection (see
    repository._ensure_skip_schema for why not inside the caller's tx)."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    path = os.path.join(os.path.dirname(__file__), "sql", "0011_supplier_whatsapp.sql")
    with open(path, encoding="utf-8") as fh:
        script = fh.read()
    with database.get_central_connection() as conn:
        ddl = conn.cursor()
        for batch in [b.strip() for b in re.split(r"^\s*GO\s*$", script, flags=re.MULTILINE) if b.strip()]:
            ddl.execute(batch)
        conn.commit()
    _SCHEMA_READY = True


def normalize_targets(targets):
    """[{name, kind}] -> cleaned list. Rule: ONE group, or 1+ contacts --
    a group always wins alone (the first one listed)."""
    clean, seen = [], set()
    for t in targets or []:
        name = " ".join(str((t or {}).get("name") or "").split())
        kind = "group" if str((t or {}).get("kind") or "").lower() == "group" else "contact"
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        clean.append({"name": name, "kind": kind})
    groups = [t for t in clean if t["kind"] == "group"]
    return groups[:1] if groups else clean


def _row_to_contact(row):
    try:
        targets = json.loads(row.TargetsJson or "[]")
    except ValueError:
        targets = []
    return {
        "supplier_code": row.SupplierCode,
        "supplier_name": (row.SupplierName or "").strip(),
        "targets": targets,
        "auto_send": bool(row.AutoSend),
        "batch_size": int(row.BatchSize or 20),
        "send_format": row.SendFormat if row.SendFormat in SEND_FORMATS else "image",
        "bill_days": int(row.BillDays or 0),
        "updated_at": row.UpdatedAt,
        "updated_by": row.UpdatedBy,
    }


_SELECT = ("SELECT SupplierCode, SupplierName, TargetsJson, AutoSend, BatchSize, SendFormat, BillDays, "
           "UpdatedAt, UpdatedBy FROM dbo.SupplierWhatsAppContact ")


def list_contacts(store_name):
    _ensure_schema()
    with database.get_central_connection() as conn:
        rows = conn.cursor().execute(_SELECT + "WHERE StoreName = ? ORDER BY SupplierName", store_name).fetchall()
    return [_row_to_contact(r) for r in rows]


def get_contact(store_name, supplier_code):
    _ensure_schema()
    with database.get_central_connection() as conn:
        row = conn.cursor().execute(_SELECT + "WHERE StoreName = ? AND SupplierCode = ?",
                                    store_name, str(supplier_code)).fetchone()
    return _row_to_contact(row) if row else None


def save_contact(store_name, supplier_code, supplier_name, targets, auto_send, batch_size,
                 send_format, bill_days, actor=None):
    """Upsert; an empty target list deletes the supplier's row."""
    _ensure_schema()
    targets = normalize_targets(targets)
    code = str(supplier_code or "").strip()
    if not code:
        raise ValueError("supplier_code is required.")
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        if not targets:
            cur.execute("DELETE FROM dbo.SupplierWhatsAppContact WHERE StoreName = ? AND SupplierCode = ?",
                        store_name, code)
            conn.commit()
            return None
        args = (
            (supplier_name or "").strip(), json.dumps(targets, ensure_ascii=False), 1 if auto_send else 0,
            max(1, min(int(batch_size or 20), 500)), send_format if send_format in SEND_FORMATS else "image",
            max(0, min(int(bill_days or 0), 30)), actor,
        )
        updated = cur.execute(
            "UPDATE dbo.SupplierWhatsAppContact SET SupplierName = ?, TargetsJson = ?, AutoSend = ?, BatchSize = ?, "
            "SendFormat = ?, BillDays = ?, UpdatedBy = ?, UpdatedAt = GETDATE() WHERE StoreName = ? AND SupplierCode = ?",
            *args, store_name, code,
        ).rowcount
        if not updated:
            cur.execute(
                "INSERT INTO dbo.SupplierWhatsAppContact (SupplierName, TargetsJson, AutoSend, BatchSize, SendFormat, "
                "BillDays, UpdatedBy, StoreName, SupplierCode) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                *args, store_name, code,
            )
        conn.commit()
    return get_contact(store_name, code)


def _current_order_id(store_name):
    with database.get_central_connection() as conn:
        return repository._latest_order_id(conn.cursor(), store_name)


def send_status(store_name, supplier_code):
    """What the auto-send needs for one supplier on the CURRENT order:
    assigned products (qty > 0) not yet sent in any batch, and the counts."""
    _ensure_schema()
    order_id = _current_order_id(store_name)
    assigned = repository.assigned_orders(store_name, supplier_code)
    codes = [_format_product_code(r.get("ProductCode")) for r in assigned]
    sent, batches, final_sent = set(), 0, False
    if order_id is not None:
        with database.get_central_connection() as conn:
            rows = conn.cursor().execute(
                "SELECT ProductCode, Kind, BatchNo FROM dbo.SupplierWhatsAppSent "
                "WHERE StoreName = ? AND OrderId = ? AND SupplierCode = ?",
                store_name, order_id, str(supplier_code),
            ).fetchall()
        for r in rows:
            if r.Kind == "batch":
                sent.add(r.ProductCode)
                batches = max(batches, int(r.BatchNo or 0))
            else:
                final_sent = True
    unsent = [c for c in codes if c not in sent]
    return {
        "order_id": order_id,
        "assigned_count": len(codes),
        "sent_count": len(codes) - len(unsent),
        "unsent_codes": unsent,
        "batches_sent": batches,
        "final_sent": final_sent,
    }


def mark_sent(store_name, supplier_code, product_codes, kind, actor=None):
    """Record a successful send. Returns the batch number used."""
    _ensure_schema()
    kind = "final" if kind == "final" else "batch"
    order_id = _current_order_id(store_name)
    if order_id is None:
        raise ValueError("This store has no current order.")
    codes = [str(c) for c in product_codes or [] if str(c).strip()]
    with database.get_central_connection() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT ISNULL(MAX(BatchNo), 0) FROM dbo.SupplierWhatsAppSent "
            "WHERE StoreName = ? AND OrderId = ? AND SupplierCode = ? AND Kind = ?",
            store_name, order_id, str(supplier_code), kind,
        ).fetchone()
        batch_no = int(row[0] or 0) + 1
        if codes:
            cur.fast_executemany = True
            cur.executemany(
                "INSERT INTO dbo.SupplierWhatsAppSent (StoreName, OrderId, SupplierCode, ProductCode, Kind, BatchNo, SentBy) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(store_name, order_id, str(supplier_code), c, kind, batch_no, actor) for c in codes],
            )
        conn.commit()
    return {"order_id": order_id, "batch_no": batch_no, "kind": kind, "count": len(codes)}


# --------------------------------------------------------------------------
# Recent bills / returns for the export footer.
# IV = purchase bill (GRN), PR = purchase return (credit note from the
# supplier). Value = sum(received x item cost) over the GRN lines.
# --------------------------------------------------------------------------

def _invoice_numbers(store_name, grns):
    """Supplier invoice numbers keyed by (GRN no, GRN date) from the platform's
    sync.Batches -- best-effort: {} when the store is not on the platform."""
    if not grns:
        return {}
    try:
        store_id = database.platform_store_id(store_name)
        if not store_id:
            return {}
        numbers = sorted({str(g) for g, _ in grns})
        start = min(d for _, d in grns)
        with pyodbc.connect(database.platform_connection_string(), timeout=15) as conn:
            rows = conn.cursor().execute(
                "SELECT GrnNumber, CAST(GrnDate AS date), MAX(InvoiceNumber) FROM sync.Batches WITH (NOLOCK) "
                f"WHERE store_id = ? AND GrnNumber IN ({', '.join('?' for _ in numbers)}) AND GrnDate >= ? "
                "GROUP BY GrnNumber, CAST(GrnDate AS date)",
                store_id, *numbers, start,
            ).fetchall()
        return {(str(r[0]), r[1]): (r[2] or "").strip() for r in rows}
    except Exception:
        logger.warning("Invoice numbers unavailable for %s", store_name, exc_info=True)
        return {}


def recent_bills(store_name, supplier_code, days):
    """{'bills': [...], 'returns': [...]} for the last `days` days (today
    included), newest first. Each: series, grn_no, date, invoice_no, items,
    qty, value."""
    days = int(days or 0)
    if days <= 0:
        return {"bills": [], "returns": [], "days": 0}
    codes = repository._supplier_codes(supplier_code) or [str(supplier_code)]
    since = datetime.date.today() - datetime.timedelta(days=days - 1)
    sql = (
        "SELECT RTRIM(pt.InvoiceSeries) AS Series, pt.Grnnumber, CAST(pt.grndate AS date) AS GrnDate, "
        "COUNT(*) AS Items, SUM(ABS(ISNULL(pt.stockreceived, 0))) AS Qty, "
        "SUM(ABS(ISNULL(pt.stockreceived, 0) * ISNULL(pt.itemcost, 0))) AS Value "
        "FROM PurchaseTrans pt WITH (NOLOCK) "
        f"WHERE pt.StoreName = ? AND pt.suppliercode IN ({', '.join('?' for _ in codes)}) "
        "AND RTRIM(pt.InvoiceSeries) IN ('IV', 'PR') AND pt.grndate >= ? "
        "GROUP BY RTRIM(pt.InvoiceSeries), pt.Grnnumber, CAST(pt.grndate AS date) "
        "ORDER BY GrnDate DESC, pt.Grnnumber DESC"
    )
    with database.get_central_connection() as conn:
        rows = conn.cursor().execute(sql, store_name, *codes, since).fetchall()
    invoice = _invoice_numbers(store_name, [(r.Grnnumber, r.GrnDate) for r in rows if r.Series == "IV"])
    out = {"bills": [], "returns": [], "days": days}
    for r in rows:
        item = {
            "series": r.Series, "grn_no": r.Grnnumber, "date": r.GrnDate,
            "invoice_no": invoice.get((str(r.Grnnumber), r.GrnDate), "") if r.Series == "IV" else "",
            "items": int(r.Items or 0), "qty": float(r.Qty or 0), "value": round(float(r.Value or 0), 2),
        }
        out["bills" if r.Series == "IV" else "returns"].append(item)
    return out


def organization_name(store_name):
    """Tenant name for the export header (platform dbo.tenants), '' if unknown."""
    try:
        with pyodbc.connect(database.platform_connection_string(), timeout=15) as conn:
            row = conn.cursor().execute(
                "SELECT TOP 1 t.tenant_name FROM dbo.stores s JOIN dbo.tenants t ON t.tenant_id = s.tenant_id "
                "WHERE s.store_code = ?",
                store_name,
            ).fetchone()
        return (row[0] or "").strip() if row else ""
    except Exception:
        return ""
