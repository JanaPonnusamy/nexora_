"""Mail a supplier's exported order to the supplier.

Sent from the tenant mailbox already configured for Supplier Mail Import
(same account + app password; SMTP host derived from its IMAP host) to the
supplier's mail id: sync.Suppliers.email, else the Mail Import override.
The attachments are exactly the files the export produced (a split / image
export's .zip is unpacked, like the desktop client does).

send_order_mail never raises: a mail failure must never fail the export
itself -- the result's status tells the client what happened.
"""
import datetime
import html
import io
import logging
import smtplib
import ssl
import zipfile
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import pyodbc

from modules.legacy_order import database
from modules.supplier_mail_import import repository as mail_repository
from modules.supplier_mail_import.mailbox import split_addresses

logger = logging.getLogger("supplier_order_mail")

SMTP_TIMEOUT_SECONDS = 60
# IMAP host -> (SMTP host, port). 465 = implicit TLS, 587 = STARTTLS.
_SMTP_BY_IMAP = {
    "imap.gmail.com": ("smtp.gmail.com", 465),
    "imap.googlemail.com": ("smtp.gmail.com", 465),
    "imap.mail.yahoo.com": ("smtp.mail.yahoo.com", 465),
    "outlook.office365.com": ("smtp.office365.com", 587),
    "imap-mail.outlook.com": ("smtp-mail.outlook.com", 587),
    "imap.zoho.com": ("smtp.zoho.com", 465),
    "imap.zoho.in": ("smtp.zoho.in", 465),
}


def smtp_endpoint(imap_host):
    host = str(imap_host or "").strip().lower()
    if host in _SMTP_BY_IMAP:
        return _SMTP_BY_IMAP[host]
    return ("smtp" + host[4:] if host.startswith("imap") else host), 465


def _store_info(store_name):
    """(tenant_id, store_id, display name) from NEXORA_PLATFORM.dbo.stores."""
    store_id = database.platform_store_id(store_name)
    if not store_id:
        return None, None, store_name
    with pyodbc.connect(database.platform_connection_string(), timeout=15) as conn:
        row = conn.cursor().execute(
            "SELECT CONVERT(varchar(40), tenant_id), LTRIM(RTRIM(ISNULL(store_name, ''))) "
            "FROM dbo.stores WHERE store_id = ?",
            store_id,
        ).fetchone()
    if not row:
        return None, store_id, store_name
    return row[0], store_id, row[1] or store_name


def supplier_addresses(store_id, supplier_code):
    """The supplier's mail id(s): master email first, then the Mail Import
    override. supplier_code may be a comma list (several codes, one supplier)."""
    codes = [c.strip() for c in str(supplier_code or "").split(",") if c.strip()]
    if not store_id or not codes:
        return []
    with pyodbc.connect(database.platform_connection_string(), timeout=15) as conn:
        rows = conn.cursor().execute(
            "SELECT LTRIM(RTRIM(ISNULL(s.email, ''))), ISNULL(m.mail_from, '') "
            "FROM sync.Suppliers s "
            "LEFT JOIN dbo.supplier_mail_import_settings m ON m.tenant_id = s.tenant_id "
            "  AND m.store_id = s.store_id AND m.supplier_code = RTRIM(CAST(s.suppliercode AS VARCHAR(100))) "
            f"WHERE s.store_id = ? AND RTRIM(CAST(s.suppliercode AS VARCHAR(100))) IN ({', '.join('?' * len(codes))})",
            store_id, *codes,
        ).fetchall()
    for master, override in rows:
        found = split_addresses(master) or split_addresses(override)
        if found:
            return found
    return []


def mail_status(store_name, supplier_code):
    """Can this supplier's order be mailed? {ready, to, reason}."""
    try:
        tenant_id, store_id, _ = _store_info(store_name)
        if not tenant_id:
            return {"ready": False, "to": [], "reason": "Store is not set up on the platform."}
        config = mail_repository.get_config(tenant_id) or {}
        to = supplier_addresses(store_id, supplier_code)
        if not config.get("imap_host") or not config.get("username") or not config.get("has_password"):
            return {"ready": False, "to": to, "reason": "Tenant mailbox is not set up (Supplier Mail Import settings)."}
        if not to:
            return {"ready": False, "to": [], "reason": "This supplier has no mail id in the supplier master."}
        return {"ready": True, "to": to, "reason": ""}
    except Exception as ex:
        logger.warning("supplier mail status failed for %s/%s: %s", store_name, supplier_code, ex)
        return {"ready": False, "to": [], "reason": f"Could not check the supplier mail id: {ex}"}


def _attachments(content, filename):
    if str(filename or "").lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            return [(name, zf.read(name)) for name in zf.namelist() if not name.endswith("/")]
    return [(filename, content)]


def _money(value):
    return f"Rs. {value:,.0f}" if value else "-"


def _body_html(details):
    rows = "".join(
        f"<tr><td style='padding:8px 14px;color:#64748b;font-size:13px;border-bottom:1px solid #eef2f7'>{html.escape(k)}</td>"
        f"<td style='padding:8px 14px;color:#0f172a;font-size:13px;font-weight:600;border-bottom:1px solid #eef2f7'>{html.escape(str(v))}</td></tr>"
        for k, v in details
    )
    return (
        "<div style='font-family:Segoe UI,Arial,sans-serif;background:#f4f6fb;padding:24px'>"
        "<div style='max-width:560px;margin:0 auto;background:#fff;border-radius:14px;overflow:hidden;"
        "box-shadow:0 4px 18px rgba(15,23,42,.08)'>"
        "<div style='background:linear-gradient(135deg,#0d9488,#2563eb);padding:18px 22px;color:#fff'>"
        "<div style='font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.85'>Purchase Order</div>"
        f"<div style='font-size:19px;font-weight:700;margin-top:4px'>{html.escape(details[0][1])}</div></div>"
        "<div style='padding:14px 8px 4px'><p style='margin:0 14px 10px;color:#334155;font-size:14px'>"
        "Dear Sir/Madam,<br>Please find our purchase order attached. Kindly supply the items at the earliest.</p>"
        f"<table style='width:100%;border-collapse:collapse'>{rows}</table>"
        "<p style='margin:14px;color:#94a3b8;font-size:11px'>Bill value is approximate (order qty x last purchase price).</p>"
        "</div></div></div>"
    )


def send_order_mail(store_name, supplier_code, supplier_name, content, filename, products, bill_value, order_no=None, actor=None):
    """Mail the export to the supplier. Returns {status, to, files, message}
    with status SENT | SKIPPED | FAILED."""
    try:
        tenant_id, store_id, store_label = _store_info(store_name)
        if not tenant_id:
            return {"status": "SKIPPED", "to": [], "files": 0, "message": "Store is not set up on the platform."}
        config = mail_repository.get_config(tenant_id, with_password=True) or {}
        if not config.get("imap_host") or not config.get("username") or not config.get("password"):
            return {"status": "SKIPPED", "to": [], "files": 0,
                    "message": "Tenant mailbox is not set up (Supplier Mail Import settings)."}
        to = supplier_addresses(store_id, supplier_code)
        if not to:
            return {"status": "SKIPPED", "to": [], "files": 0,
                    "message": f"{supplier_name} has no mail id in the supplier master."}

        files = _attachments(content, filename)
        now = datetime.datetime.now()
        when = now.strftime("%d-%m-%Y %I:%M %p")
        supplier = " ".join(str(supplier_name or supplier_code).split())
        store_text = store_label if store_label.upper() == store_name.upper() else f"{store_label} ({store_name})"
        subject = (
            f"Purchase Order - {store_text} - {supplier} - {len(files)} attachment{'' if len(files) == 1 else 's'}"
            f" - {when} - {products} product{'' if products == 1 else 's'}, approx {_money(bill_value)}"
        )
        details = [
            ("Store", store_text),
            ("Supplier", f"{supplier} ({supplier_code})"),
            ("Order no", order_no or "-"),
            ("Products", products),
            ("Approx. bill value", _money(bill_value)),
            ("Attachments", f"{len(files)} - " + ", ".join(name for name, _ in files)),
            ("Sent at", when),
        ] + ([("Sent by", actor)] if actor else [])

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((store_text, config["username"]))
        msg["To"] = ", ".join(to)
        msg["Message-ID"] = make_msgid()
        msg.set_content("\n".join(f"{k}: {v}" for k, v in details)
                        + "\n\nPlease find our purchase order attached.\n(Bill value is approximate.)")
        msg.add_alternative(_body_html(details), subtype="html")
        for name, data in files:
            maintype, subtype = ("image", "png") if name.lower().endswith(".png") else ("application", "octet-stream")
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)

        host, port = smtp_endpoint(config["imap_host"])
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS, context=context) as smtp:
                smtp.login(config["username"], config["password"])
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
                smtp.starttls(context=context)
                smtp.login(config["username"], config["password"])
                smtp.send_message(msg)
        logger.info("order mail sent: store=%s supplier=%s to=%s files=%s", store_name, supplier_code, to, len(files))
        return {"status": "SENT", "to": to, "files": len(files), "message": f"Mailed to {', '.join(to)}."}
    except smtplib.SMTPAuthenticationError:
        return {"status": "FAILED", "to": [], "files": 0,
                "message": "Mailbox sign-in failed for sending. Check the app password in Supplier Mail Import settings."}
    except Exception as ex:
        logger.exception("order mail failed for %s/%s", store_name, supplier_code)
        return {"status": "FAILED", "to": [], "files": 0, "message": f"Order mail failed: {ex}"}
