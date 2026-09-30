"""EmailSenderTransport (store side): SMTP send + the IMAP retry/ack-dedupe
fix -- remove_result() must actually mark the source message \\Seen (it was
previously a documented no-op, so ACKs were re-fetched and re-processed on
every cycle forever), and upload() must refuse an oversized package instead
of attempting a broken send.

No real mailbox: imaplib.IMAP4_SSL and smtplib.SMTP are mocked at the
module level the transport imports them from.
"""
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["NEXORA_TEST_SMTP_PASSWORD"] = "secret"

from store_agent.file_transfer import email_transport as et

_CFG = {
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "imap_host": "imap.example.com",
    "imap_port": 993,
    "imap_folder": "INBOX",
    "username": "nma-sync@example.com",
    "password_env": "NEXORA_TEST_SMTP_PASSWORD",
    "to_address": "ho-sync@example.com",
}


def _fake_imap_with_one_result(package_id="pkg-1", store_id="STORE-1"):
    """Builds a mock IMAP4_SSL connection exposing exactly one UNSEEN
    NEXORA-RESULT message, and returns (mock_class, mock_conn) so the test
    can assert on conn.store(...) calls after remove_result()."""
    import email as email_mod
    msg = email_mod.message.EmailMessage()
    msg["Subject"] = "NEXORA-RESULT %s %s" % (store_id, package_id)
    msg.add_attachment(b'{"package_id": "%s"}' % package_id.encode(),
                        maintype="application", subtype="json",
                        filename="%s.json" % package_id)
    raw = msg.as_bytes()

    conn = mock.MagicMock()
    conn.search.return_value = ("OK", [b"42"])
    conn.fetch.return_value = ("OK", [(b"42 (RFC822 {n}}", raw)])
    conn.logout.return_value = ("BYE", [])

    cls = mock.MagicMock(return_value=conn)
    return cls, conn


def test_upload_rejects_oversized_package():
    cfg = dict(_CFG, max_attachment_bytes=10)
    transport = et.EmailSenderTransport(cfg, store_id="STORE-1")
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"x" * 100)
        path = tmp.name
    try:
        try:
            transport.upload(path, "pkg-1.zip")
            assert False, "expected RuntimeError"
        except RuntimeError as ex:
            assert "PACKAGE_TOO_LARGE" in str(ex)
    finally:
        os.remove(path)


def test_upload_within_limit_sends():
    cfg = dict(_CFG, max_attachment_bytes=1000)
    transport = et.EmailSenderTransport(cfg, store_id="STORE-1")
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"x" * 100)
        path = tmp.name
    try:
        with mock.patch.object(et, "smtplib") as smtp_mod:
            smtp_conn = mock.MagicMock()
            smtp_mod.SMTP.return_value.__enter__.return_value = smtp_conn
            transport.upload(path, "pkg-1.zip")
            smtp_conn.send_message.assert_called_once()
    finally:
        os.remove(path)


def test_remove_result_marks_source_message_seen_not_reprocessed_forever():
    cls, conn = _fake_imap_with_one_result()
    transport = et.EmailSenderTransport(dict(_CFG), store_id="STORE-1")
    with mock.patch.object(et, "imaplib") as imap_mod:
        imap_mod.IMAP4_SSL = cls

        results = transport.list_results()
        assert [name for name, _ in results] == ["pkg-1.json"]
        for _, local_path in results:
            os.remove(local_path)

        # Before the fix this was a no-op: the message was never marked
        # \Seen anywhere, so it would be re-fetched by list_results() on
        # every subsequent cycle indefinitely.
        conn.store.assert_not_called()
        transport.remove_result("pkg-1.json")
        conn.store.assert_called_once_with("42", "+FLAGS", "\\Seen")


def test_remove_result_ignores_unknown_name():
    transport = et.EmailSenderTransport(dict(_CFG), store_id="STORE-1")
    transport.remove_result("never-seen.json")  # must not raise
