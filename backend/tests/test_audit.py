import json
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from modules.audit.models import (
    ActorRole,
    AuditCategory,
    AuditEntry,
    AuditFilterParams,
    AuditImmutableError,
    AuditStatus,
)
from modules.audit.repository import (
    AuditRepository,
    build_filter_query,
    _parse_date_bound,
)
from modules.audit.redaction import (
    _is_secret_key,
    redact_and_bound_metadata,
    _sanitize_value,
    MAX_DEPTH,
    MAX_STRING_LENGTH,
    MAX_ARRAY_WIDTH,
)
from modules.audit.context import (
    AuditContext,
    parse_device_info,
    resolve_local_country,
)
from modules.audit.taxonomy import (
    category_for_action,
    lookup_endpoint_action,
    AUDITED_ENDPOINTS,
    UNAUDITED_ENDPOINTS,
)
from modules.audit.writer import record_audit, record_audit_strict
from modules.audit.diff import compute_mutation_diff


class TestAuditModelAndImmutability(unittest.TestCase):
    """Test data model constraints and immutability guards."""

    def test_immutability_guards_reject_mutations(self):
        repo = AuditRepository()
        with self.assertRaises(AuditImmutableError):
            repo.update("log-123", {"action": "tampered"})

        with self.assertRaises(AuditImmutableError):
            repo.delete("log-123")

        with self.assertRaises(AuditImmutableError):
            repo.upsert("log-123", {"action": "tampered"})

        with self.assertRaises(AuditImmutableError):
            repo.replace("log-123", {"action": "tampered"})

        with self.assertRaises(AuditImmutableError):
            repo.save("log-123")

    def test_audit_entry_model_validation(self):
        entry = AuditEntry(
            action="user.create",
            category="user",
            actor_role=ActorRole.ADMIN,
            status=AuditStatus.SUCCESS,
        )
        self.assertEqual(entry.action, "user.create")
        self.assertEqual(entry.category, "user")
        self.assertEqual(entry.actor_role, ActorRole.ADMIN)
        self.assertEqual(entry.status, AuditStatus.SUCCESS)
        self.assertIsNotNone(entry.timestamp)


class TestAuditRedactionAndBounding(unittest.TestCase):
    """Test recursive secret redaction and payload bounding."""

    def test_secret_key_matching(self):
        self.assertTrue(_is_secret_key("password"))
        self.assertTrue(_is_secret_key("passwd"))
        self.assertTrue(_is_secret_key("secret"))
        self.assertTrue(_is_secret_key("token"))
        self.assertTrue(_is_secret_key("api_key"))
        self.assertTrue(_is_secret_key("apiKey"))
        self.assertTrue(_is_secret_key("private_key"))
        self.assertTrue(_is_secret_key("credential"))
        self.assertTrue(_is_secret_key("authcode"))
        self.assertTrue(_is_secret_key("cvv"))
        self.assertTrue(_is_secret_key("mfa"))
        self.assertTrue(_is_secret_key("user_password"))
        self.assertTrue(_is_secret_key("jwt_token"))

        self.assertFalse(_is_secret_key("username"))
        self.assertFalse(_is_secret_key("email"))
        self.assertFalse(_is_secret_key("store_name"))

    def test_nested_secret_redaction(self):
        raw_metadata = {
            "username": "alice",
            "password": "SuperSecretPassword123!",
            "nested": {
                "api_key": "sk-1234567890",
                "deep": {
                    "token": "bearer-token-abc",
                    "safe_val": "hello",
                },
            },
            "credentials": ["secret1", "secret2"],
        }
        redacted_json = redact_and_bound_metadata(raw_metadata)
        data = json.loads(redacted_json)

        self.assertEqual(data["username"], "alice")
        self.assertEqual(data["password"], "[redacted]")
        self.assertEqual(data["nested"]["api_key"], "[redacted]")
        self.assertEqual(data["nested"]["deep"]["token"], "[redacted]")
        self.assertEqual(data["nested"]["deep"]["safe_val"], "hello")
        self.assertEqual(data["credentials"], "[redacted]")

    def test_string_length_bounding(self):
        long_str = "x" * 500
        sanitized = _sanitize_value(long_str, depth=1)
        self.assertTrue(len(sanitized) < 400)
        self.assertTrue(sanitized.endswith("... [truncated]"))

    def test_array_width_bounding(self):
        large_list = list(range(100))
        sanitized = _sanitize_value(large_list, depth=1)
        self.assertEqual(len(sanitized), 26)  # 25 items + 1 truncation notification
        self.assertTrue("75 more items truncated" in sanitized[-1])

    def test_recursion_depth_bounding(self):
        deep_obj = {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}
        sanitized = _sanitize_value(deep_obj, depth=1)
        self.assertEqual(
            sanitized["a"]["b"]["c"]["d"],
            "[Max depth reached]",
        )


class TestAuditRequestContext(unittest.TestCase):
    """Test client IP, country classification, and user agent parsing."""

    def test_parse_device_info(self):
        mac_chrome = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.assertEqual(parse_device_info(mac_chrome), "Chrome (macOS)")

        win_edge = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        self.assertEqual(parse_device_info(win_edge), "Edge (Windows)")

        win_firefox = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0"
        self.assertEqual(parse_device_info(win_firefox), "Firefox (Windows)")

        ios_safari = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1"
        self.assertEqual(parse_device_info(ios_safari), "Safari (iOS)")

        self.assertIsNone(parse_device_info(None))
        self.assertIsNone(parse_device_info(""))

    def test_local_country_resolution_never_external(self):
        # Private / loopback addresses must resolve to None without network calls
        self.assertIsNone(resolve_local_country("127.0.0.1"))
        self.assertIsNone(resolve_local_country("192.168.1.100"))
        self.assertIsNone(resolve_local_country("10.0.0.1"))
        self.assertIsNone(resolve_local_country("172.16.0.1"))
        self.assertIsNone(resolve_local_country("::1"))
        self.assertIsNone(resolve_local_country("invalid-ip"))
        self.assertIsNone(resolve_local_country(None))


class TestActionTaxonomy(unittest.TestCase):
    """Test action category derivation and endpoint mappings."""

    def test_category_derivation_from_prefix(self):
        self.assertEqual(category_for_action("user.create"), "user")
        self.assertEqual(category_for_action("role.permission.update"), "role")
        self.assertEqual(category_for_action("sync.table.status.update"), "sync")
        self.assertEqual(category_for_action("tenant.update"), "tenant")
        self.assertEqual(category_for_action("store.create"), "store")
        self.assertEqual(category_for_action("audit.export"), "audit")

    def test_category_overrides(self):
        self.assertEqual(category_for_action("login"), "auth")
        self.assertEqual(category_for_action("logout"), "auth")
        self.assertEqual(category_for_action("setup_login"), "auth")
        self.assertEqual(category_for_action("export"), "audit")

    def test_unknown_action_fallback(self):
        # Must NEVER throw; fallback to system
        self.assertEqual(category_for_action("custom_unknown_action"), "system")
        self.assertEqual(category_for_action(""), "system")
        self.assertEqual(category_for_action(None), "system")

    def test_audited_endpoints_matching(self):
        spec = lookup_endpoint_action("POST", "/api/users")
        self.assertIsNotNone(spec)
        self.assertEqual(spec["action"], "user.create")
        self.assertEqual(spec["category"], "user")

        spec_param = lookup_endpoint_action("PUT", "/api/users/12345")
        self.assertIsNotNone(spec_param)
        self.assertEqual(spec_param["action"], "user.update")

        self.assertIn("POST /api/auth/login", AUDITED_ENDPOINTS)
        self.assertIn("GET /api/sync/tasks/pending/{store_id}", UNAUDITED_ENDPOINTS)


class TestAuditWriterEntryPoints(unittest.TestCase):
    """Test record_audit (never throws) vs record_audit_strict (throws)."""

    @patch("modules.audit.writer._repo.insert")
    def test_record_audit_never_throws_on_db_error(self, mock_insert):
        mock_insert.side_effect = RuntimeError("Database connection lost")
        # Should not raise exception
        result = record_audit(
            ctx=None,
            action="user.create",
            target_id="123",
            reason="Test create",
        )
        self.assertIsNone(result)

    @patch("modules.audit.writer._repo.insert")
    def test_record_audit_strict_propagates_exception(self, mock_insert):
        mock_insert.side_effect = RuntimeError("Database connection lost")
        with self.assertRaises(RuntimeError):
            record_audit_strict(
                ctx=None,
                action="auth.login.success",
                target_id="123",
                reason="Strict login audit",
            )


class TestMutationDiffing(unittest.TestCase):
    """Test before-after diff calculation and secret field handling."""

    def test_diff_changed_fields(self):
        before = {"username": "alice", "full_name": "Alice Smith", "email": "alice@old.com"}
        inputs = {"username": "alice", "full_name": "Alice Cooper"}

        changed, diff = compute_mutation_diff(before, inputs)
        self.assertEqual(changed, ["full_name"])
        self.assertEqual(diff["full_name"]["old"], "Alice Smith")
        self.assertEqual(diff["full_name"]["new"], "Alice Cooper")

    def test_diff_secret_fields_without_exposing_values(self):
        before = {"username": "alice", "password": "old_hash"}
        inputs = {"username": "alice", "password": "new_plain_password"}

        changed, diff = compute_mutation_diff(before, inputs)
        self.assertIn("password", changed)
        self.assertEqual(diff["password"]["old"], "[redacted]")
        self.assertEqual(diff["password"]["new"], "[redacted]")


class TestFilterBuilderAndDateParsing(unittest.TestCase):
    """Test query building, substring search, enum dropping, and UTC date widening."""

    def test_date_bound_widening(self):
        # Start date: 00:00:00.000
        start = _parse_date_bound("2026-08-15", is_end=False)
        self.assertEqual(start.year, 2026)
        self.assertEqual(start.month, 8)
        self.assertEqual(start.day, 15)
        self.assertEqual(start.hour, 0)
        self.assertEqual(start.minute, 0)
        self.assertEqual(start.second, 0)

        # End date: 23:59:59.999
        end = _parse_date_bound("2026-08-15", is_end=True)
        self.assertEqual(end.year, 2026)
        self.assertEqual(end.month, 8)
        self.assertEqual(end.day, 15)
        self.assertEqual(end.hour, 23)
        self.assertEqual(end.minute, 59)
        self.assertEqual(end.second, 59)
        self.assertEqual(end.microsecond, 999000)

    def test_invalid_date_rejection(self):
        with self.assertRaises(ValueError):
            _parse_date_bound("invalid-date")

        with self.assertRaises(ValueError):
            params = AuditFilterParams(from_date="2026-08-20", to_date="2026-08-10")
            build_filter_query(params)

    def test_shared_filter_builder(self):
        params = AuditFilterParams(
            search="testuser",
            category="user",
            status="success",
            actor_role="admin",
            from_date="2026-08-01",
            to_date="2026-08-15",
        )
        where_sql, sql_params = build_filter_query(params)

        self.assertIn("actor_name LIKE ?", where_sql)
        self.assertIn("category = ?", where_sql)
        self.assertIn("status = ?", where_sql)
        self.assertIn("actor_role = ?", where_sql)
        self.assertIn("timestamp >= ?", where_sql)
        self.assertIn("timestamp <= ?", where_sql)

    def test_invalid_enum_dropped_safely(self):
        params = AuditFilterParams(
            category="INVALID_CATEGORY_NAME",
            status="INVALID_STATUS",
            actor_role="INVALID_ROLE",
        )
        where_sql, sql_params = build_filter_query(params)
        # Invalid enum values should not be injected into WHERE clause
        self.assertEqual(where_sql, "")
        self.assertEqual(len(sql_params), 0)


if __name__ == "__main__":
    unittest.main()
