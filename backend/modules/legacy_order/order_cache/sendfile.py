"""Offline fallback transport for the order cache file: when a store PC has
no direct HO connection, its .sqlite cache is sent as a WhatsApp attachment
(or email) to the admin, who gets it onto the store PC however the network
allows and imports it there -- or, in reverse, downloads it on HO and
imports it locally with the same /order-cache/{store}/import endpoint.

Deliberately self-contained (does not reuse modules.sync.file_transfer_*):
that pipeline is a general zip+manifest+checksum package system built for
whole sync.* table deltas across many tables. This is a single small file
(one SQLite db, a few KB-MB) going out as one attachment -- reusing the
bigger pipeline would couple this feature to infrastructure it doesn't
need. WhatsApp is the primary channel (reuses the same send_message/profile
convention as modules.sync.health_monitor's admin alert); email is a
best-effort fallback via plain SMTP env vars, same spirit as
modules.password_reset.service's mailer.
"""
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def _whatsapp_recipient():
    from modules.sync import health_monitor
    return health_monitor._alert_phone()


def _send_whatsapp(store_name, file_path):
    profile_id, phone = _whatsapp_recipient()
    if not profile_id or not phone:
        return {"ok": False, "channel": "whatsapp", "error": "no WhatsApp profile/phone configured"}
    from modules.whatsapp import service as wa
    with open(file_path, "rb") as fh:
        content = fh.read()
    filename = f"order_cache_{store_name}.sqlite"
    message = (
        f"NEXORA ORDER CACHE — {store_name}\n"
        "Store PC has no direct HO connection. Import this file on HO via "
        "Sync > Order Cache Monitor > Import (same screen either direction)."
    )
    try:
        result = wa.send_message(profile_id, phone, message, attachment_name=filename, attachment_content=content)
    except Exception as exc:
        logger.exception("order cache WhatsApp send failed for %s", store_name)
        return {"ok": False, "channel": "whatsapp", "error": str(exc)}
    ok = (result or {}).get("status") == "sent"
    return {"ok": ok, "channel": "whatsapp", "detail": result}


def _send_email(store_name, file_path):
    host = os.environ.get("NEXORA_SMTP_HOST", "").strip()
    to_addr = os.environ.get("NEXORA_ORDER_CACHE_ALERT_EMAIL", "").strip()
    if not host or not to_addr:
        return {"ok": False, "channel": "email", "error": "NEXORA_SMTP_HOST / NEXORA_ORDER_CACHE_ALERT_EMAIL not configured"}
    port = int(os.environ.get("NEXORA_SMTP_PORT", "587"))
    user = os.environ.get("NEXORA_SMTP_USER", "")
    password = os.environ.get("NEXORA_SMTP_PASSWORD", "")
    from_addr = os.environ.get("NEXORA_SMTP_FROM", user or "nexora@localhost")

    msg = EmailMessage()
    msg["Subject"] = f"Nexora order cache — {store_name} (no HO connection)"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(
        f"Store PC '{store_name}' has no direct HO connection.\n"
        "Import the attached .sqlite file on HO via Sync > Order Cache Monitor > Import."
    )
    filename = f"order_cache_{store_name}.sqlite"
    with open(file_path, "rb") as fh:
        msg.add_attachment(fh.read(), maintype="application", subtype="x-sqlite3", filename=filename)

    try:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return {"ok": True, "channel": "email"}
    except Exception as exc:
        logger.exception("order cache email send failed for %s", store_name)
        return {"ok": False, "channel": "email", "error": str(exc)}


def send_cache_file(store_name, file_path, channel="whatsapp"):
    if channel == "email":
        return _send_email(store_name, file_path)
    return _send_whatsapp(store_name, file_path)
