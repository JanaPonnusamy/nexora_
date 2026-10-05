"""EmailReceiverTransport (HO side): the IMAP retry fix.

Previously list_incoming() marked every fetched message \\Seen
unconditionally, before its import outcome was known. A package that failed
validation or import would already be \\Seen, so the next poll's UNSEEN
search would never surface it again -- silently defeating the retry
behaviour file_transfer_receiver_service.py relies on (see
PROJECT_DETAIL.md §33, "known limitation").

Now \\Seen is only set in archive_incoming(), which the receiver service
calls only for terminal outcomes (imported / duplicate / rejected / a
post-validation import failure) -- never for a transient validation-stage
failure, which must stay unseen so it is retried automatically.

No real mailbox: imaplib.IMAP4_SSL and smtplib.SMTP are mocked at the
module level the transport imports them from.
"""
import email as email_mod
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["NEXORA_TEST_IMAP_PASSWORD"] = "secret"

from modules.sync.file_transfer_transport import email as ho_email

_CFG = {
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_folder": "INBOX",
    "username": "ho-sync@example.com",
    "password_env": "NEXORA_TEST_IMAP_PASSWORD",
    "default_store_address": "nma-sync@example.com",
}


def _fake_conn_with_one_package(store_id="STORE-1", package_id="pkg-1"):
    msg = email_mod.message.EmailMessage()
    msg["Subject"] = "NEXORA-SYNC %s %s" % (store_id, package_id)
    msg.add_attachment(b"fake zip bytes", maintype="application", subtype="zip",
                        filename="%s.zip" % package_id)
    raw = msg.as_bytes()

    conn = mock.MagicMock()
    conn.search.return_value = ("OK", [b"7"])
    conn.fetch.return_value = ("OK", [(b"7 (RFC822 {n}}", raw)])
    conn.logout.return_value = ("BYE", [])
    return mock.MagicMock(return_value=conn), conn


def test_list_incoming_does_not_mark_seen():
    cls, conn = _fake_conn_with_one_package()
    transport = ho_email.EmailReceiverTransport(dict(_CFG))
    with mock.patch.object(ho_email, "imaplib") as imap_mod:
        imap_mod.IMAP4_SSL = cls
        found = transport.list_incoming()
        assert [name for name, _ in found] == ["STORE-1/pkg-1.zip"]
        for _, local_path in found:
            os.remove(local_path)
        conn.store.assert_not_called()


def test_archive_incoming_marks_the_correct_message_seen():
    cls, conn = _fake_conn_with_one_package()
    transport = ho_email.EmailReceiverTransport(dict(_CFG))
    with mock.patch.object(ho_email, "imaplib") as imap_mod:
        imap_mod.IMAP4_SSL = cls
        found = transport.list_incoming()
        for _, local_path in found:
            os.remove(local_path)

        transport.archive_incoming("STORE-1/pkg-1.zip", success=True)
        conn.store.assert_called_once_with("7", "+FLAGS", "\\Seen")


def test_transient_failure_leaves_message_unseen_for_retry():
    """Mirrors file_transfer_receiver_service._import_one's contract: a
    transient FAILED outcome at the validation stage never calls
    archive_incoming, so the message must remain unseen."""
    cls, conn = _fake_conn_with_one_package()
    transport = ho_email.EmailReceiverTransport(dict(_CFG))
    with mock.patch.object(ho_email, "imaplib") as imap_mod:
        imap_mod.IMAP4_SSL = cls
        found = transport.list_incoming()
        for _, local_path in found:
            os.remove(local_path)
        # No archive_incoming() call here -- simulates a transient failure.
        conn.store.assert_not_called()


def test_archive_incoming_ignores_unknown_name():
    transport = ho_email.EmailReceiverTransport(dict(_CFG))
    transport.archive_incoming("STORE-1/never-listed.zip", success=True)  # must not raise
