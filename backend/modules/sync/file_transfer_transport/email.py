"""Email receiver transport: the HO half of store_agent/file_transfer/
email_transport.py's protocol. Authenticated SMTP (STARTTLS) to send results,
IMAP (SSL) to poll for incoming packages -- both stdlib. Credentials are
always read from an environment variable named in config.

Subject grammar (must match the store-agent side exactly):
    Store -> HO : "NEXORA-SYNC <store_id> <package_id>"   (attachment: .zip)
    HO -> Store : "NEXORA-RESULT <store_id> <package_id>" (attachment: .json)
"""
import email
import imaplib
import os
import re
import smtplib
import tempfile
from email.message import EmailMessage

from modules.sync.file_transfer_transport.base import ReceiverTransport

_SYNC_SUBJECT_RE = re.compile(r"^NEXORA-SYNC\s+(\S+)\s+(\S+)$")


def _password(cfg, key="password_env"):
    env_name = cfg.get(key)
    if not env_name:
        raise RuntimeError("email transport config requires '%s'" % key)
    value = os.environ.get(env_name)
    if not value:
        raise RuntimeError("environment variable '%s' is not set" % env_name)
    return value


def _fetch_matching(cfg, subject_re):
    """Fetch (but never mark \\Seen) unread messages whose subject matches.
    Marking \\Seen is the caller's responsibility once a message's outcome is
    terminal (see EmailReceiverTransport.archive_incoming) -- doing it here,
    unconditionally on fetch, is what caused the previous known retry bug: a
    package that failed validation/import would already be \\Seen and the
    next poll's UNSEEN search would never surface it again."""
    host = cfg.get("imap_host")
    port = int(cfg.get("imap_port", 993))
    folder = cfg.get("imap_folder", "INBOX")
    out = []
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(cfg.get("username"), _password(cfg))
        conn.select(folder)
        status, data = conn.search(None, "UNSEEN")
        if status != "OK":
            return out
        for uid in data[0].split():
            status, msg_data = conn.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            parsed = email.message_from_bytes(msg_data[0][1])
            subject = (parsed.get("Subject") or "").strip()
            match = subject_re.match(subject)
            if not match:
                continue
            for part in parsed.walk():
                filename = part.get_filename()
                if not filename:
                    continue
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                suffix = os.path.splitext(filename)[1] or ".bin"
                tmp = tempfile.NamedTemporaryFile(
                    prefix="nexora_mail_", suffix=suffix, delete=False
                )
                tmp.write(payload)
                tmp.close()
                out.append((uid.decode(), match.groups(), tmp.name, filename))
                break
        return out
    finally:
        conn.logout()


def _mark_seen(cfg, uid):
    host = cfg.get("imap_host")
    port = int(cfg.get("imap_port", 993))
    folder = cfg.get("imap_folder", "INBOX")
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(cfg.get("username"), _password(cfg))
        conn.select(folder)
        conn.store(uid, "+FLAGS", "\\Seen")
    finally:
        conn.logout()


def _send(cfg, subject, to_address, attachment_path, attachment_name):
    msg = EmailMessage()
    msg["From"] = cfg.get("username")
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content("Nexora automated sync message. Do not reply by hand.")
    with open(attachment_path, "rb") as fh:
        data = fh.read()
    subtype = "zip" if attachment_name.endswith(".zip") else "json"
    msg.add_attachment(data, maintype="application", subtype=subtype, filename=attachment_name)

    host = cfg.get("smtp_host")
    port = int(cfg.get("smtp_port", 587))
    with smtplib.SMTP(host, port, timeout=60) as smtp:
        smtp.starttls()
        smtp.login(cfg.get("username"), _password(cfg))
        smtp.send_message(msg)


class EmailReceiverTransport(ReceiverTransport):
    def __init__(self, cfg):
        self.cfg = cfg
        # remote_name -> IMAP uid, so archive_incoming (called only once this
        # package's outcome is terminal) knows which physical message to mark
        # \Seen. Instance-scoped: list_incoming()/archive_incoming() are
        # always called within the same receiver tick (file_transfer_
        # receiver_service.run_tick), never across process restarts.
        self._incoming_uids = {}

    def list_incoming(self):
        out = []
        for uid, groups, local_path, filename in _fetch_matching(self.cfg, _SYNC_SUBJECT_RE):
            store_id = groups[0]
            remote_name = store_id + "/" + filename
            self._incoming_uids[remote_name] = uid
            out.append((remote_name, local_path))
        return out

    def archive_incoming(self, remote_name, success):
        """Mark the source message \\Seen. Called by
        file_transfer_receiver_service._import_one only for terminal
        outcomes (IMPORTED, DUPLICATE, REJECTED, or a post-validation import
        FAILURE) -- a transient validation-stage FAILED never reaches here,
        so that message stays unseen and the next poll's UNSEEN search picks
        it back up. This is what makes automatic retry actually work; the
        previous implementation marked \\Seen unconditionally in
        list_incoming(), before the outcome was known, which silently
        defeated retry for every failed package (see PROJECT_DETAIL.md §33)."""
        uid = self._incoming_uids.pop(remote_name, None)
        if uid is None:
            return
        try:
            _mark_seen(self.cfg, uid)
        except Exception:
            # Best-effort: if this fails, the message is re-fetched next
            # poll. Re-processing is safe -- checksum/package_id idempotency
            # in file_transfer_repository guards against a duplicate import
            # regardless of IMAP \Seen state.
            pass

    def send_result(self, store_id, result_filename, local_path):
        package_id = os.path.splitext(result_filename)[0]
        subject = "NEXORA-RESULT %s %s" % (store_id, package_id)
        # Per-store reply routing requires a store_id -> email mapping this
        # first cut does not model; a single configured mailbox stands in
        # for every store today (see docs known-limitations).
        to_address = self.cfg.get("default_store_address")
        if not to_address:
            raise RuntimeError(
                "email transport config requires 'default_store_address' to "
                "send results back to stores"
            )
        _send(self.cfg, subject, to_address, local_path, result_filename)
