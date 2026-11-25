"""Read-only IMAP access to a tenant's mailbox.

The folder is opened with readonly=True and every fetch uses BODY.PEEK, so
the poller never marks a mail read, moves or deletes it -- the people using
the mailbox see it exactly as before.
"""
import datetime
import email
import email.policy
import email.utils
import imaplib
import re

TIMEOUT_SECONDS = 60
EXCEL_EXTENSIONS = (".xls", ".xlsx", ".xlsm")
_ADDRESS = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def split_addresses(text):
    """'a@x.com; b@y.com' -> ['a@x.com', 'b@y.com'] (invalid entries dropped)."""
    parts = re.split(r"[,;\s]+", str(text or ""))
    return [p.strip().lower() for p in parts if _ADDRESS.match(p.strip())]


def valid_address_list(text):
    """True when every non-blank entry is a mail address."""
    parts = [p for p in re.split(r"[,;\s]+", str(text or "")) if p.strip()]
    return all(_ADDRESS.match(p.strip()) for p in parts)


class Mailbox:
    def __init__(self, config):
        self.config = config
        self.conn = None

    def __enter__(self):
        cfg = self.config
        host, port = cfg["imap_host"], int(cfg.get("imap_port") or (993 if cfg.get("use_ssl", True) else 143))
        cls = imaplib.IMAP4_SSL if cfg.get("use_ssl", True) else imaplib.IMAP4
        try:
            self.conn = cls(host, port, timeout=TIMEOUT_SECONDS)
        except TypeError:  # Python < 3.9 has no timeout argument
            self.conn = cls(host, port)
        if not cfg.get("use_ssl", True):
            self.conn.starttls()
        self.conn.login(cfg["username"], cfg["password"])
        folder = cfg.get("folder") or "INBOX"
        status, data = self.conn.select(_quote(folder), readonly=True)
        if status != "OK":
            raise RuntimeError(f"Mail folder '{folder}' not found.")
        self.message_count = int(data[0] or 0)
        return self

    def __exit__(self, *exc):
        try:
            self.conn.logout()
        except Exception:
            pass

    def find(self, addresses, since_days, subject_filter=""):
        """Mails from any of addresses received in the last since_days,
        newest first: [{uid, message_id, from, subject, date}]."""
        since = (datetime.date.today() - datetime.timedelta(days=max(int(since_days), 1))).strftime("%d-%b-%Y")
        uids = set()
        for address in addresses:
            status, data = self.conn.uid("SEARCH", None, "FROM", _quote(address), "SINCE", since)
            if status == "OK" and data and data[0]:
                uids.update(data[0].split())
        mails = []
        for uid in uids:
            status, data = self.conn.uid(
                "FETCH", uid, "(INTERNALDATE BODY.PEEK[HEADER.FIELDS (MESSAGE-ID DATE SUBJECT FROM)])"
            )
            raw = _first_payload(data) if status == "OK" else None
            if raw is None:
                continue
            header = email.message_from_bytes(raw, policy=email.policy.default)
            sender = email.utils.parseaddr(str(header.get("From", "")))[1].lower()
            # IMAP FROM is a substring match; keep only exact senders.
            if sender not in addresses:
                continue
            subject = str(header.get("Subject", "") or "")
            if subject_filter and subject_filter.lower() not in subject.lower():
                continue
            mails.append({
                "uid": uid,
                "message_id": str(header.get("Message-ID", "") or "").strip()
                or f"<uid-{uid.decode()}@{self.config.get('folder') or 'INBOX'}>",
                "from": sender,
                "subject": subject,
                "date": _mail_date(header.get("Date"), data),
            })
        mails.sort(key=lambda m: m["date"] or datetime.datetime.min, reverse=True)
        return mails

    def excel_attachments(self, uid):
        """[(filename, bytes)] for every Excel attachment of the mail."""
        status, data = self.conn.uid("FETCH", uid, "(BODY.PEEK[])")
        raw = _first_payload(data) if status == "OK" else None
        if raw is None:
            return []
        message = email.message_from_bytes(raw, policy=email.policy.default)
        found = []
        for part in message.walk():
            filename = part.get_filename()
            if not filename or not filename.lower().endswith(EXCEL_EXTENSIONS):
                continue
            payload = part.get_payload(decode=True)
            if payload:
                found.append((filename, payload))
        return found


def _quote(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _first_payload(data):
    for item in data or []:
        if isinstance(item, tuple) and len(item) > 1:
            return item[1]
    return None


def _mail_date(header_date, fetch_data):
    """Local naive datetime (the DB stores GETDATE()-style local times):
    the Date header, falling back to the server's INTERNALDATE."""
    value = None
    try:
        value = email.utils.parsedate_to_datetime(str(header_date)) if header_date else None
    except (TypeError, ValueError):
        value = None
    if value is None:
        for item in fetch_data or []:
            head = item[0] if isinstance(item, tuple) else item
            if isinstance(head, bytes) and b"INTERNALDATE" in head:
                parsed = imaplib.Internaldate2tuple(head)
                if parsed:
                    value = datetime.datetime(*parsed[:6])
                break
    if value is not None and value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value
