"""Email transport: SFTP/file-drop are not always available (no IT-provisioned
share, no SFTP endpoint) but a mailbox almost always is. Uses authenticated
SMTP (STARTTLS) to send and IMAP (SSL) to poll -- both stdlib, no extra
dependency. Credentials are always read from an environment variable named in
config, never stored in the config file itself.

Message convention (both directions use the same subject grammar so the
counterparty can find its own messages in a shared/dedicated mailbox without
parsing arbitrary sender addresses):

    Store -> HO : subject "NEXORA-SYNC <store_id> <package_id>"
                  one attachment: the package .zip
    HO -> Store : subject "NEXORA-RESULT <store_id> <package_id>"
                  one attachment: the result .json
"""
import email
import imaplib
import os
import re
import smtplib
import tempfile
from email.message import EmailMessage

from store_agent.file_transfer.transport_base import SenderTransport

_SYNC_SUBJECT_RE = re.compile(r"^NEXORA-SYNC\s+(\S+)\s+(\S+)$")
_RESULT_SUBJECT_RE = re.compile(r"^NEXORA-RESULT\s+(\S+)\s+(\S+)$")


def _password(cfg, key="password_env"):
    env_name = cfg.get(key)
    if not env_name:
        raise RuntimeError("email transport config requires '%s'" % key)
    value = os.environ.get(env_name)
    if not value:
        raise RuntimeError("environment variable '%s' is not set" % env_name)
    return value


def _send(cfg, subject, to_address, attachment_path, attachment_name):
    msg = EmailMessage()
    msg["From"] = cfg.get("username")
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content("Nexora automated sync message. Do not reply by hand.")
    with open(attachment_path, "rb") as fh:
        data = fh.read()
    maintype = "application"
    subtype = "zip" if attachment_name.endswith(".zip") else "json"
    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=attachment_name)

    host = cfg.get("smtp_host")
    port = int(cfg.get("smtp_port", 587))
    with smtplib.SMTP(host, port, timeout=60) as smtp:
        smtp.starttls()
        smtp.login(cfg.get("username"), _password(cfg))
        smtp.send_message(msg)


def _fetch_matching(cfg, subject_re):
    """Return [(uid, subject_match_groups, local_temp_path, attachment_name)]
    for unread messages in the configured IMAP folder whose subject matches
    subject_re and which carry exactly one attachment."""
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
            raw = msg_data[0][1]
            parsed = email.message_from_bytes(raw)
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
                break  # one attachment per message by convention
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


class EmailSenderTransport(SenderTransport):
    def __init__(self, cfg, store_id):
        self.cfg = cfg
        self.store_id = str(store_id)
        self.to_address = cfg.get("to_address")
        if not self.to_address:
            raise RuntimeError("email transport config requires 'to_address' (HO inbox)")
        # filename -> IMAP uid, populated by list_results() and consumed by
        # remove_result() within the same dispatcher cycle (see
        # sync_dispatcher.FileTransferSyncDispatcher._process_results).
        self._result_uids = {}

    def upload(self, local_path, remote_name):
        max_bytes = int(self.cfg.get("max_attachment_bytes") or 0)
        if max_bytes:
            size = os.path.getsize(local_path)
            if size > max_bytes:
                # Raising here is deliberate: the caller (sync_dispatcher's
                # _flush_pending) catches this and calls outbox.mark_failed,
                # which keeps the package durably in the outbox (not
                # silently dropped) for an operator to resize/split or
                # switch transport -- never attempts a truncated send.
                raise RuntimeError(
                    "PACKAGE_TOO_LARGE: %s is %d bytes, exceeds configured "
                    "max_attachment_bytes=%d" % (remote_name, size, max_bytes)
                )
        package_id = os.path.splitext(remote_name)[0]
        subject = "NEXORA-SYNC %s %s" % (self.store_id, package_id)
        _send(self.cfg, subject, self.to_address, local_path, remote_name)

    def list_results(self):
        results = []
        for uid, groups, local_path, filename in _fetch_matching(self.cfg, _RESULT_SUBJECT_RE):
            store_id = groups[0]
            if store_id != self.store_id:
                continue
            self._result_uids[filename] = uid
            results.append((filename, local_path))
        return results

    def remove_result(self, remote_name):
        """Mark the source message \\Seen once sync_dispatcher has durably
        recorded the ACK (outbox.mark_acknowledged). Previously a no-op that
        relied on a message being marked \\Seen during list_results() --
        which never actually happened, so every ACK was re-fetched and
        re-processed on every cycle forever. mark_acknowledged is idempotent,
        so that was not corrupting, but it meant the mailbox never converged
        and IMAP was re-polled for the same messages indefinitely."""
        uid = self._result_uids.pop(remote_name, None)
        if uid is None:
            return
        try:
            _mark_seen(self.cfg, uid)
        except Exception:
            # Best-effort: worst case this ACK is re-fetched next cycle,
            # which is safe (mark_acknowledged is idempotent on package_id).
            pass


