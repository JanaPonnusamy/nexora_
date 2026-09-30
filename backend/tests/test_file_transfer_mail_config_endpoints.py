"""file_transfer_admin_controller mail-config endpoints (Phase 2 extraction):
a VIEW of the env-var-driven HO mail config (never returns the password
itself, only whether its named env var is set) plus real SMTP/IMAP
connection tests -- never a fabricated success.

Called directly as plain functions (not through TestClient/app) since these
handlers take no request body and only depend on get_current_user, which
FastAPI would otherwise require a running app + DB to satisfy.
"""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controllers import file_transfer_admin_controller as controller

_EMAIL_CFG = {
    "smtp_host": "smtp.example.com", "smtp_port": 587,
    "imap_host": "imap.example.com", "imap_port": 993, "imap_folder": "INBOX",
    "username": "ho-sync@example.com", "password_env": "NEXORA_TEST_HO_MAIL_PW",
    "default_store_address": "nma-sync@example.com",
}


def test_get_mail_config_never_returns_password():
    with mock.patch.object(controller.cfg, "enabled", return_value=True), \
         mock.patch.object(controller.cfg, "transport_config",
                            return_value={"mode": "EMAIL", "email": _EMAIL_CFG}):
        os.environ["NEXORA_TEST_HO_MAIL_PW"] = "super-secret"
        try:
            result = controller.get_mail_config(user=None)
        finally:
            del os.environ["NEXORA_TEST_HO_MAIL_PW"]

    assert result["password_env"] == "NEXORA_TEST_HO_MAIL_PW"
    assert result["password_env_set"] is True
    assert "super-secret" not in str(result)
    assert result["smtp_host"] == "smtp.example.com"


def test_get_mail_config_reports_unset_password_env():
    with mock.patch.object(controller.cfg, "enabled", return_value=True), \
         mock.patch.object(controller.cfg, "transport_config",
                            return_value={"mode": "EMAIL", "email": _EMAIL_CFG}):
        os.environ.pop("NEXORA_TEST_HO_MAIL_PW", None)
        result = controller.get_mail_config(user=None)
    assert result["password_env_set"] is False


def test_test_smtp_rejects_when_mode_is_not_email():
    with mock.patch.object(controller.cfg, "transport_config",
                            return_value={"mode": "FILE_DROP"}):
        result = controller.test_smtp(user=None)
    assert result.ok is False
    assert "EMAIL" in result.detail


def test_test_smtp_reports_real_connection_failure_not_fake_success():
    with mock.patch.object(controller.cfg, "transport_config",
                            return_value={"mode": "EMAIL", "email": _EMAIL_CFG}):
        os.environ["NEXORA_TEST_HO_MAIL_PW"] = "x"
        try:
            with mock.patch.object(controller.smtplib, "SMTP",
                                    side_effect=OSError("connection refused")):
                result = controller.test_smtp(user=None)
        finally:
            del os.environ["NEXORA_TEST_HO_MAIL_PW"]
    assert result.ok is False
    assert "connection refused" in result.detail


def test_test_smtp_reports_success_when_connection_succeeds():
    with mock.patch.object(controller.cfg, "transport_config",
                            return_value={"mode": "EMAIL", "email": _EMAIL_CFG}):
        os.environ["NEXORA_TEST_HO_MAIL_PW"] = "x"
        try:
            with mock.patch.object(controller, "smtplib") as smtp_mod:
                smtp_conn = mock.MagicMock()
                smtp_mod.SMTP.return_value.__enter__.return_value = smtp_conn
                result = controller.test_smtp(user=None)
        finally:
            del os.environ["NEXORA_TEST_HO_MAIL_PW"]
    assert result.ok is True
    smtp_conn.login.assert_called_once()


def test_test_imap_reports_real_connection_failure_not_fake_success():
    with mock.patch.object(controller.cfg, "transport_config",
                            return_value={"mode": "EMAIL", "email": _EMAIL_CFG}):
        os.environ["NEXORA_TEST_HO_MAIL_PW"] = "x"
        try:
            with mock.patch.object(controller.imaplib, "IMAP4_SSL",
                                    side_effect=OSError("dns failure")):
                result = controller.test_imap(user=None)
        finally:
            del os.environ["NEXORA_TEST_HO_MAIL_PW"]
    assert result.ok is False
    assert "dns failure" in result.detail
