import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from modules.mobile_bff import service
from modules.mobile_bff.repository import hash_token
from modules.mobile_bff.schemas import DeviceInfo

_USER = {
    "user_id": "11111111-1111-1111-1111-111111111111",
    "username": "fielduser",
    "first_name": "Field",
    "is_platform_user": False,
    "tenant_id": "22222222-2222-2222-2222-222222222222",
    "modules": [],
    "roles": [
        {
            "role_id": "33333333-3333-3333-3333-333333333333",
            "role_name": "STORE_USER",
            "store_id": "44444444-4444-4444-4444-444444444444",
            "store_code": "NMA",
            "store_name": "Nathan Medicals A",
        }
    ],
}

_DEVICE = DeviceInfo(
    device_id="device-abcdef123456",
    device_name="iPhone 17",
    platform="ios",
    app_version="0.1.0",
)


def _future():
    return (datetime.now(timezone.utc) + timedelta(days=10)).replace(tzinfo=None)


def _past():
    return (datetime.now(timezone.utc) - timedelta(days=1)).replace(tzinfo=None)


class TokenHashingTests(unittest.TestCase):
    def test_hash_is_stable_and_not_the_raw_token(self):
        raw = "some-refresh-token-value"
        digest = hash_token(raw)
        self.assertEqual(digest, hash_token(raw))
        self.assertNotIn(raw, digest)
        self.assertEqual(len(digest), 64)

    def test_different_tokens_hash_differently(self):
        self.assertNotEqual(hash_token("token-a"), hash_token("token-b"))


class HandshakeTests(unittest.TestCase):
    def test_reports_version_and_supported_build_range(self):
        result = service.handshake()
        self.assertEqual(result["api_version"], service.API_VERSION)
        self.assertLessEqual(
            result["min_supported_build"], result["latest_build"]
        )
        self.assertIn("auth.refresh", result["features"])
        self.assertTrue(result["server_time"])


@patch("modules.mobile_bff.service.repository")
@patch("modules.mobile_bff.service.AuthService")
class LoginTests(unittest.TestCase):
    def test_bad_credentials_return_none(self, auth_service, repo):
        auth_service.return_value.login.return_value = None
        self.assertIsNone(service.login("who", "wrong", _DEVICE))
        repo.issue.assert_not_called()

    def test_successful_login_returns_both_tokens(self, auth_service, repo):
        auth_service.return_value.login.return_value = _USER
        repo.issue.return_value = {
            "token": "refresh-raw",
            "token_id": "t-1",
            "expires_at": _future(),
        }
        repo.REFRESH_TOKEN_TTL_DAYS = 30

        result = service.login("fielduser", "pw", _DEVICE)

        self.assertEqual(result["refresh_token"], "refresh-raw")
        self.assertEqual(result["token_type"], "bearer")
        self.assertTrue(result["token"])
        self.assertEqual(result["user"]["username"], "fielduser")
        self.assertGreater(result["expires_in"], 0)

    def test_login_supersedes_any_existing_chain_for_the_device(
        self, auth_service, repo
    ):
        # Otherwise signing in repeatedly would leave several 30-day refresh
        # tokens valid for the same device at once.
        auth_service.return_value.login.return_value = _USER
        repo.issue.return_value = {
            "token": "r",
            "token_id": "t",
            "expires_at": _future(),
        }
        repo.REFRESH_TOKEN_TTL_DAYS = 30

        service.login("fielduser", "pw", _DEVICE)

        repo.revoke_device.assert_called_once_with(
            _USER["user_id"], _DEVICE.device_id, "superseded-by-login"
        )


@patch("modules.mobile_bff.service.repository")
@patch("modules.mobile_bff.service.AuthService")
class RefreshTests(unittest.TestCase):
    def _live_record(self):
        return {
            "token_id": "t-old",
            "user_id": _USER["user_id"],
            "device_id": _DEVICE.device_id,
            "expires_at": _future(),
            "revoked_at": None,
        }

    def test_unknown_token_is_rejected(self, auth_service, repo):
        repo.find.return_value = None
        with self.assertRaises(service.SessionError) as ctx:
            service.refresh("nope", _DEVICE.device_id)
        self.assertFalse(ctx.exception.reuse_detected)

    def test_rotation_revokes_the_presented_token_and_issues_a_new_one(
        self, auth_service, repo
    ):
        repo.find.return_value = self._live_record()
        auth_service.return_value.get_by_id.return_value = _USER
        repo.issue.return_value = {
            "token": "refresh-new",
            "token_id": "t-new",
            "expires_at": _future(),
        }
        repo.REFRESH_TOKEN_TTL_DAYS = 30

        result = service.refresh("refresh-old", _DEVICE.device_id)

        repo.revoke.assert_called_once_with("t-old", "rotated")
        self.assertEqual(result["refresh_token"], "refresh-new")
        self.assertEqual(repo.issue.call_args.kwargs["replaces"], "t-old")

    def test_replaying_a_rotated_token_burns_the_whole_device_chain(
        self, auth_service, repo
    ):
        # A second presentation of an already-rotated token means the value
        # leaked, so revoking only that link would leave the thief's newer
        # token alive.
        record = self._live_record()
        record["revoked_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        repo.find.return_value = record

        with self.assertRaises(service.SessionError) as ctx:
            service.refresh("refresh-old", _DEVICE.device_id)

        self.assertTrue(ctx.exception.reuse_detected)
        repo.revoke_device.assert_called_once_with(
            _USER["user_id"], _DEVICE.device_id, "reuse-detected"
        )

    def test_a_token_replayed_from_another_device_is_rejected(
        self, auth_service, repo
    ):
        repo.find.return_value = self._live_record()

        with self.assertRaises(service.SessionError) as ctx:
            service.refresh("refresh-old", "device-somewhere-else")

        self.assertTrue(ctx.exception.reuse_detected)
        repo.revoke_device.assert_called_once_with(
            _USER["user_id"], _DEVICE.device_id, "device-mismatch"
        )

    def test_expired_token_is_rejected_without_issuing(self, auth_service, repo):
        record = self._live_record()
        record["expires_at"] = _past()
        repo.find.return_value = record

        with self.assertRaises(service.SessionError):
            service.refresh("refresh-old", _DEVICE.device_id)
        repo.issue.assert_not_called()

    def test_a_deactivated_user_cannot_refresh(self, auth_service, repo):
        repo.find.return_value = self._live_record()
        auth_service.return_value.get_by_id.return_value = None

        with self.assertRaises(service.SessionError):
            service.refresh("refresh-old", _DEVICE.device_id)

        repo.revoke_device.assert_called_once_with(
            _USER["user_id"], _DEVICE.device_id, "user-inactive"
        )
        repo.issue.assert_not_called()


@patch("modules.mobile_bff.service.repository")
class LogoutTests(unittest.TestCase):
    def test_logout_by_refresh_token_revokes_that_device(self, repo):
        repo.find.return_value = {
            "token_id": "t-1",
            "user_id": _USER["user_id"],
            "device_id": _DEVICE.device_id,
            "expires_at": _future(),
            "revoked_at": None,
        }
        repo.revoke_device.return_value = 1

        revoked = service.logout(_USER["user_id"], raw_token="refresh-raw")

        self.assertEqual(revoked, 1)
        repo.revoke_device.assert_called_once_with(
            _USER["user_id"], _DEVICE.device_id, "logout"
        )

    def test_a_token_belonging_to_someone_else_revokes_nothing(self, repo):
        repo.find.return_value = {
            "token_id": "t-1",
            "user_id": "99999999-9999-9999-9999-999999999999",
            "device_id": _DEVICE.device_id,
            "expires_at": _future(),
            "revoked_at": None,
        }

        self.assertEqual(
            service.logout(_USER["user_id"], raw_token="someone-elses"), 0
        )
        repo.revoke_device.assert_not_called()

    def test_logout_all_devices_walks_every_live_session(self, repo):
        repo.list_devices.return_value = [
            {"device_id": "d-1"},
            {"device_id": "d-2"},
        ]
        repo.revoke_device.return_value = 1

        self.assertEqual(
            service.logout(_USER["user_id"], all_devices=True), 2
        )
        self.assertEqual(repo.revoke_device.call_count, 2)

    def test_logout_with_no_identifier_is_a_no_op(self, repo):
        self.assertEqual(service.logout(_USER["user_id"]), 0)
        repo.revoke_device.assert_not_called()


if __name__ == "__main__":
    unittest.main()
