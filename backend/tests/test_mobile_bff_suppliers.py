"""The mobile supplier list.

The point of this endpoint is the role it serves: `/api/supplier-stock-analysis/
suppliers` is behind `require_admin_role`, which 403s a login whose roles are
all purchase manager and/or salesman — the field roles the mobile app targets.
Those users saw an empty supplier list and no reason for it.

These tests pin both halves of that: the roles the admin gate rejects are
served here, and the scope a client could otherwise widen is still closed.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from dependencies.store_scope import is_supplier_analysis_blocked
from modules.mobile_bff.router import suppliers

_TENANT = "22222222-2222-2222-2222-222222222222"
_STORE = "44444444-4444-4444-4444-444444444444"

# A purchase-manager login: exactly the shape the admin gate turns away.
_FIELD_CLAIMS = {
    "sub": "11111111-1111-1111-1111-111111111111",
    "username": "purchase.manager",
    "tenant_id": _TENANT,
    "store_id": _STORE,
    "is_platform_user": False,
    "role_names": ["PURCHASE MANAGER"],
}

_FIELD_USER = {
    "user_id": _FIELD_CLAIMS["sub"],
    "username": "purchase.manager",
    "tenant_id": _TENANT,
}

_SUPPLIERS = {
    "suppliers": [
        {"supplier_code": "SUP-2041", "supplier_name": "Sri Balaji Pharma"},
        {"supplier_code": "SUP-3102", "supplier_name": "Kumar Medical Agencies"},
    ]
}


def _auth_service(user=_FIELD_USER):
    service = MagicMock()
    service.return_value.get_by_id.return_value = user
    return service


class RoleAccessTests(unittest.TestCase):
    def test_the_admin_gate_really_does_block_this_role(self):
        # Guards the premise. If this ever stops being true, the endpoint below
        # has no reason to exist and should be reconsidered, not left running.
        self.assertTrue(is_supplier_analysis_blocked(_FIELD_CLAIMS))

    @patch("modules.mobile_bff.router.supplier_service")
    @patch("modules.mobile_bff.router.AuthService", new_callable=_auth_service)
    def test_a_purchase_manager_gets_their_suppliers(self, _auth, supplier_service):
        supplier_service.list_suppliers.return_value = _SUPPLIERS

        result = suppliers(search="", store_id=None, current_user=_FIELD_CLAIMS)

        self.assertEqual(result, _SUPPLIERS)
        supplier_service.list_suppliers.assert_called_once_with(_TENANT, _STORE, "")

    @patch("modules.mobile_bff.router.supplier_service")
    @patch("modules.mobile_bff.router.AuthService", new_callable=_auth_service)
    def test_search_is_passed_through(self, _auth, supplier_service):
        supplier_service.list_suppliers.return_value = {"suppliers": []}

        suppliers(search="balaji", store_id=None, current_user=_FIELD_CLAIMS)

        supplier_service.list_suppliers.assert_called_once_with(
            _TENANT, _STORE, "balaji"
        )

    @patch("modules.mobile_bff.router.supplier_service")
    @patch("modules.mobile_bff.router.AuthService", new_callable=_auth_service)
    def test_the_response_shape_the_client_already_parses_is_unchanged(
        self, _auth, supplier_service
    ):
        # The mobile repository reads `suppliers` as a full snapshot and
        # reconciles absent rows as deletions; a reshaped payload here would
        # silently empty the local cache.
        supplier_service.list_suppliers.return_value = _SUPPLIERS

        result = suppliers(search="", store_id=None, current_user=_FIELD_CLAIMS)

        self.assertIn("suppliers", result)
        self.assertEqual(len(result["suppliers"]), 2)


class ScopeTests(unittest.TestCase):
    def test_there_is_no_tenant_parameter_to_tamper_with(self):
        # The admin-tier endpoint takes tenant_id as a query parameter and
        # checks it after the fact. This one does not offer it at all: scope is
        # resolved from the account, so widening it is not expressible.
        import inspect

        params = inspect.signature(suppliers).parameters
        self.assertNotIn("tenant_id", params)
        self.assertEqual(set(params), {"search", "store_id", "current_user"})

    @patch("modules.mobile_bff.router.supplier_service")
    @patch("modules.mobile_bff.router.AuthService", new_callable=_auth_service)
    def test_a_token_claiming_a_tenant_the_account_does_not_have_is_refused(
        self, _auth, supplier_service
    ):
        # The tenant is read from the user record and then checked against the
        # token's own claim. A token signed with a tenant the account does not
        # hold — the §1.1 forged-token case — is refused rather than served
        # from whichever value happened to win.
        claims = {**_FIELD_CLAIMS, "tenant_id": "a-tenant-the-token-claims"}

        with self.assertRaises(HTTPException) as raised:
            suppliers(search="", store_id=None, current_user=claims)

        self.assertEqual(raised.exception.status_code, 403)
        supplier_service.list_suppliers.assert_not_called()

    @patch("modules.mobile_bff.router.supplier_service")
    @patch("modules.mobile_bff.router.AuthService", new_callable=_auth_service)
    def test_a_store_may_be_narrowed_within_the_users_own_tenant(
        self, _auth, supplier_service
    ):
        supplier_service.list_suppliers.return_value = {"suppliers": []}

        suppliers(search="", store_id="another-store", current_user=_FIELD_CLAIMS)

        self.assertEqual(
            supplier_service.list_suppliers.call_args[0][1], "another-store"
        )

    @patch("modules.mobile_bff.router.supplier_service")
    @patch(
        "modules.mobile_bff.router.AuthService",
        new_callable=lambda: _auth_service({"user_id": "x", "tenant_id": "other-tenant"}),
    )
    def test_a_token_from_another_tenant_is_refused(self, _auth, supplier_service):
        with self.assertRaises(HTTPException) as raised:
            suppliers(search="", store_id=None, current_user=_FIELD_CLAIMS)

        self.assertEqual(raised.exception.status_code, 403)
        supplier_service.list_suppliers.assert_not_called()

    @patch("modules.mobile_bff.router.supplier_service")
    @patch(
        "modules.mobile_bff.router.AuthService",
        new_callable=lambda: _auth_service(None),
    )
    def test_an_unknown_account_is_not_served(self, _auth, supplier_service):
        with self.assertRaises(HTTPException) as raised:
            suppliers(search="", store_id=None, current_user=_FIELD_CLAIMS)

        self.assertEqual(raised.exception.status_code, 404)
        supplier_service.list_suppliers.assert_not_called()

    @patch("modules.mobile_bff.router.supplier_service")
    @patch(
        "modules.mobile_bff.router.AuthService",
        new_callable=lambda: _auth_service({"user_id": "x", "tenant_id": None}),
    )
    def test_a_tenantless_account_is_told_why_rather_than_served_everything(
        self, _auth, supplier_service
    ):
        # A platform user has no tenant of their own. Falling back to "all
        # suppliers" would hand one login every tenant's supplier master.
        claims = {**_FIELD_CLAIMS, "tenant_id": None, "is_platform_user": True}

        with self.assertRaises(HTTPException) as raised:
            suppliers(search="", store_id=None, current_user=claims)

        self.assertEqual(raised.exception.status_code, 400)
        supplier_service.list_suppliers.assert_not_called()


if __name__ == "__main__":
    unittest.main()
