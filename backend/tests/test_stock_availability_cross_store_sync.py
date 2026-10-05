"""Regression tests for cross-store product-selection sync (Stock Availability).

BUG REPRODUCED: clicking NMW -> "BRIV 25MG  TAB" left NMA/NMG showing a STALE
selection from a previous click instead of updating to the equivalent BRIV
25MG product. Root cause traced end-to-end (see PR description / commit
message): the feature had been implemented in frontend/ (the web SPA), but
the desktop Electron client the bug was reproduced in
(desktop/supplier-stock-client) has its own, separate React tree and was
never wired to the sync endpoint at all — so no request was ever made from
that app. Fixed by wiring desktop/supplier-stock-client/src/App.jsx's
handleProductSelect to call the same backend endpoint.

While tracing the fix against the REAL tenant/store data (tenant
A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D, stores NMW/NMA/NMG/NMS/NMV), a second,
independent bug was found and is regression-tested here: the FUZZY tier had
no brand check, so "BRIV 100MG TAB" (no NMV candidate of the same brand)
fuzzy-matched onto "BRIVATOP 100MG TAB" — a different product that merely
shares strength/unit/dosage-form and a name prefix. Fixed by requiring the
parsed brand to agree (when both sides have one) before auto-accepting a
FUZZY match.

The store catalogs below are frozen snapshots of the real BRIV product
family from that tenant (captured while debugging), not synthetic data, so
these tests fail if the matching/guard logic regresses on the exact
real-world case that was reported broken.
"""

import unittest
from unittest.mock import patch

from modules.stock_availability import service

NMW = "DEB4780E-CA8D-4CCD-9942-3ACE1CC88EE0"
NMA = "109339ED-7A1D-49BF-8CC1-4FDAEE46CDC1"
NMG = "3019101A-24A6-4045-AB7E-964046383EA2"
NMS = "D55F8A0D-C230-44EA-BF56-02F143B948BD"
NMV = "4A2CEFF0-13C5-484C-B263-DE297E1E23E3"
TENANT = "A7EB45BD-BDD7-4EE6-BD7B-61D1C7F4305D"

SUPER_ADMIN_USER = {"tenant_id": None, "role_names": ["SUPER_ADMIN"], "is_platform_user": True}

# Frozen snapshot of the real BRIV family per store (captured from
# sync.Products via product_mapping.source_repository.load_store_products
# against the actual reported-broken tenant/store combination).
CATALOG = {
    NMW: [
        {"product_code": "5884053", "product_name": "BRIV 100MG  TAB", "mrp": 576.18},
        {"product_code": "5884054", "product_name": "BRIV 50MG  TAB", "mrp": 295.24},
        {"product_code": "5884055", "product_name": "BRIV 75MG  TAB", "mrp": 266.0},
        {"product_code": "5886702", "product_name": "BRIV 25MG  TAB", "mrp": 95.64},
        {"product_code": "5887140", "product_name": "BRIV SYP  100ML", "mrp": 393.25},
    ],
    NMA: [
        {"product_code": "5883025", "product_name": "BRIV 25MG", "mrp": 95.64},
        {"product_code": "5883034", "product_name": "BRIV 50MG", "mrp": 295.24},
        {"product_code": "5883102", "product_name": "BRIV 100MG", "mrp": 614.6},
        {"product_code": "5883873", "product_name": "BRIV 75MG", "mrp": 301.63},
        {"product_code": "5884066", "product_name": "BRIV 100ML", "mrp": 405.46},
    ],
    NMG: [
        # NMG shares NMW's product codes for this family (same warehouse-fed catalog).
        {"product_code": "5884053", "product_name": "BRIV 100MG  TAB", "mrp": 576.18},
        {"product_code": "5884054", "product_name": "BRIV 50MG  TAB", "mrp": 295.24},
        {"product_code": "5884055", "product_name": "BRIV 75MG  TAB", "mrp": 266.0},
        {"product_code": "5886702", "product_name": "BRIV 25MG  TAB", "mrp": 95.64},
        {"product_code": "5887140", "product_name": "BRIV SYP  100ML", "mrp": 393.25},
    ],
    NMS: [
        # NMS genuinely has no 100MG entry — must stay unmatched, never fabricated.
        {"product_code": "5852078", "product_name": "BRIV 50MG TAB", "mrp": 295.24},
        {"product_code": "5883139", "product_name": "BRIV 75MG", "mrp": 301.63},
        {"product_code": "5884023", "product_name": "BRIV 25MG", "mrp": 95.64},
    ],
    NMV: [
        # NMV has no plain 25/75/100 MG BRIV — only 50MG, 25(spaced)MG, and a
        # DIFFERENT product family "BRIVATOP" that must never be confused with it.
        {"product_code": "43126", "product_name": "BRIV 50MG TAB", "mrp": 295.24},
        {"product_code": "44320", "product_name": "BRIV 25 MG TAB", "mrp": 92.75},
        {"product_code": "43271", "product_name": "BRIVATOP 100MG TAB", "mrp": 448.0},
    ],
}

ALL_TARGETS = [NMA, NMG, NMS, NMV]


def _fake_products(tenant_id, store_id):
    return CATALOG.get(store_id, [])


def _fake_pairs(tenant_id, source_store_id, target_store_id):
    return []


def _run(source_code, source_name, targets=ALL_TARGETS, supplier_pairs=_fake_pairs):
    with patch.object(service.mapping_source_repository, "load_store_products", _fake_products), \
         patch.object(service.mapping_source_repository, "load_supplier_pairs", supplier_pairs), \
         patch.object(service.mapping_repository, "load_active_terms", lambda tenant_id: set()):
        result = service.match_cross_store_selection(
            SUPER_ADMIN_USER, TENANT, NMW, source_code, source_name, targets,
        )
    return {r["store_id"]: r for r in result["results"]}


class TestCrossStoreSyncReproducedBug(unittest.TestCase):
    """The exact screenshot scenario: NMW -> BRIV 25MG TAB."""

    def test_briv_25mg_tab_syncs_every_other_store(self):
        by_store = _run("5886702", "BRIV 25MG  TAB")

        self.assertEqual(by_store[NMA]["product"]["product_code"], "5883025")
        self.assertEqual(by_store[NMA]["match_type"], "STRONG_ATTRIBUTE_MATCH")

        self.assertEqual(by_store[NMG]["product"]["product_code"], "5886702")
        self.assertIn(by_store[NMG]["match_type"], ("EXACT_NORMALIZED_NAME", "EXACT_SUPPLIER_MATCH"))

        self.assertEqual(by_store[NMS]["product"]["product_code"], "5884023")
        self.assertEqual(by_store[NMS]["match_type"], "STRONG_ATTRIBUTE_MATCH")

        self.assertEqual(by_store[NMV]["product"]["product_code"], "44320")
        self.assertEqual(by_store[NMV]["match_type"], "EXACT_NORMALIZED_NAME")


class TestCrossStoreSyncNotHardcodedForOneProduct(unittest.TestCase):
    """Same source store, different strengths — proves sync isn't hardcoded."""

    def test_briv_100mg_tab_syncs_correctly_and_never_fabricates(self):
        by_store = _run("5884053", "BRIV 100MG  TAB")

        self.assertEqual(by_store[NMA]["product"]["product_code"], "5883102")
        self.assertEqual(by_store[NMG]["product"]["product_code"], "5884053")
        # NMS has no 100MG BRIV at all — must be left unmatched, never fabricated.
        self.assertIsNone(by_store[NMS]["product"])
        self.assertEqual(by_store[NMS]["match_type"], "NO_MATCH")

    def test_briv_50mg_tab_syncs_every_other_store(self):
        by_store = _run("5884054", "BRIV 50MG  TAB")

        self.assertEqual(by_store[NMA]["product"]["product_code"], "5883034")
        self.assertEqual(by_store[NMG]["product"]["product_code"], "5884054")
        self.assertEqual(by_store[NMS]["product"]["product_code"], "5852078")
        self.assertEqual(by_store[NMV]["product"]["product_code"], "43126")

    def test_briv_75mg_tab_syncs_every_other_store(self):
        by_store = _run("5884055", "BRIV 75MG  TAB")

        self.assertEqual(by_store[NMA]["product"]["product_code"], "5883873")
        self.assertEqual(by_store[NMG]["product"]["product_code"], "5884055")
        self.assertEqual(by_store[NMS]["product"]["product_code"], "5883139")
        # NMV carries no 75MG BRIV — must stay unmatched.
        self.assertIsNone(by_store[NMV]["product"])


class TestCrossStoreSyncNeverConfusesDifferentProducts(unittest.TestCase):
    """CRITICAL regression: a different brand/strength/unit must never be
    auto-selected just because it shares some attributes or a name prefix."""

    def test_100mg_never_matches_a_different_brand_that_shares_strength_and_form(self):
        # Found while debugging the reported bug against real data: NMV has no
        # plain BRIV 100MG, only "BRIVATOP 100MG TAB" (a different product).
        # The FUZZY tier's score alone (80.96, comfortably above the auto-select
        # threshold) used to let this through — the brand guard must block it.
        by_store = _run("5884053", "BRIV 100MG  TAB")
        self.assertIsNone(by_store[NMV]["product"])
        self.assertEqual(by_store[NMV]["match_type"], "NO_MATCH")

    def test_different_strength_is_never_treated_as_a_match(self):
        # Only a 75MG candidate exists — a 100MG source must not settle for it.
        targets_only_75 = {NMV: [{"product_code": "9", "product_name": "BRIV 75MG TAB", "mrp": None}]}
        with patch.object(service.mapping_source_repository, "load_store_products",
                           lambda tenant_id, store_id: targets_only_75.get(store_id, [])), \
             patch.object(service.mapping_source_repository, "load_supplier_pairs", _fake_pairs), \
             patch.object(service.mapping_repository, "load_active_terms", lambda tenant_id: set()):
            result = service.match_cross_store_selection(
                SUPER_ADMIN_USER, TENANT, NMW, "1", "BRIV 100MG TAB", [NMV],
            )
        self.assertEqual(result["results"][0]["match_type"], "NO_MATCH")
        self.assertIsNone(result["results"][0]["product"])

    def test_different_dosage_form_is_never_treated_as_a_match(self):
        targets_only_syrup = {NMV: [{"product_code": "9", "product_name": "BRIV 100MG SYRUP", "mrp": None}]}
        with patch.object(service.mapping_source_repository, "load_store_products",
                           lambda tenant_id, store_id: targets_only_syrup.get(store_id, [])), \
             patch.object(service.mapping_source_repository, "load_supplier_pairs", _fake_pairs), \
             patch.object(service.mapping_repository, "load_active_terms", lambda tenant_id: set()):
            result = service.match_cross_store_selection(
                SUPER_ADMIN_USER, TENANT, NMW, "1", "BRIV 100MG TAB", [NMV],
            )
        self.assertEqual(result["results"][0]["match_type"], "NO_MATCH")

    def test_different_unit_is_never_treated_as_a_match(self):
        # BRIV 100MG TAB vs BRIV 100ML — same digits, different unit (MG vs ML).
        targets_only_ml = {NMV: [{"product_code": "9", "product_name": "BRIV 100ML", "mrp": None}]}
        with patch.object(service.mapping_source_repository, "load_store_products",
                           lambda tenant_id, store_id: targets_only_ml.get(store_id, [])), \
             patch.object(service.mapping_source_repository, "load_supplier_pairs", _fake_pairs), \
             patch.object(service.mapping_repository, "load_active_terms", lambda tenant_id: set()):
            result = service.match_cross_store_selection(
                SUPER_ADMIN_USER, TENANT, NMW, "1", "BRIV 100MG TAB", [NMV],
            )
        self.assertEqual(result["results"][0]["match_type"], "NO_MATCH")


class TestCrossStoreSyncSupplierMatchPriority(unittest.TestCase):
    """SupplierProductMatch wins over a *plausible* different name/format
    (e.g. two ways of writing the same brand), but is NOT trusted blindly —
    a pairing whose target has a totally unrelated name is rejected and the
    remaining phases get a chance to find a real equivalent instead. See
    TestCrossStoreSyncRejectsBadSupplierPairing below for why: a stale/wrong
    (SupplierCode, SupplierProductCode) collision in one store's data used to
    let a wildly wrong product get auto-selected at 100% confidence."""

    def test_supplier_pair_wins_when_target_name_is_plausibly_the_same_product(self):
        def pairs(tenant_id, source_store_id, target_store_id):
            return [("5886702", "9")] if target_store_id == NMA else []

        def products(tenant_id, store_id):
            if store_id == NMA:
                return [{"product_code": "9", "product_name": "BRIV 25 MG TABLET", "mrp": 10.0}]
            return []

        with patch.object(service.mapping_source_repository, "load_store_products", products), \
             patch.object(service.mapping_source_repository, "load_supplier_pairs", pairs), \
             patch.object(service.mapping_repository, "load_active_terms", lambda tenant_id: set()):
            result = service.match_cross_store_selection(
                SUPER_ADMIN_USER, TENANT, NMW, "5886702", "BRIV 25MG  TAB", [NMA],
            )
        self.assertEqual(result["results"][0]["match_type"], "EXACT_SUPPLIER_MATCH")
        self.assertEqual(result["results"][0]["product"]["product_code"], "9")
        self.assertEqual(result["results"][0]["score"], 100.0)

    def test_supplier_pair_with_completely_unrelated_target_name_is_rejected(self):
        def pairs(tenant_id, source_store_id, target_store_id):
            return [("5886702", "9")] if target_store_id == NMA else []

        def products(tenant_id, store_id):
            if store_id == NMA:
                return [{"product_code": "9", "product_name": "COMPLETELY UNRELATED LABEL", "mrp": 10.0}]
            return []

        with patch.object(service.mapping_source_repository, "load_store_products", products), \
             patch.object(service.mapping_source_repository, "load_supplier_pairs", pairs), \
             patch.object(service.mapping_repository, "load_active_terms", lambda tenant_id: set()):
            result = service.match_cross_store_selection(
                SUPER_ADMIN_USER, TENANT, NMW, "5886702", "BRIV 25MG  TAB", [NMA],
            )
        self.assertEqual(result["results"][0]["match_type"], "NO_MATCH")
        self.assertIsNone(result["results"][0]["product"])


class TestCrossStoreSyncRejectsBadSupplierPairing(unittest.TestCase):
    """Reproduces a real bug found live against tenant Nathan Medicals: a
    stale/wrong SupplierProductMatch row for store NMS paired NMA's
    "TELMA BETA 25" (an antihypertensive) to NMS product 1638 "EMADINE AT"
    (an eye-drop, a completely different medicine) via the same
    (SupplierCode, SupplierProductCode) key. Because SUPPLIER matches were
    trusted unconditionally, clicking the source row auto-selected EMADINE AT
    at 100% confidence with zero name/attribute sanity check. Fixed by
    applying the same brand/attribute guard FUZZY already gets, and — since a
    SUPPLIER hit claims the whole source row before EXACT/NORMALIZED/
    STRUCTURED/FUZZY get a chance to run — retrying the match with that bad
    pairing excluded so a real equivalent already in the store's own catalog
    still gets found."""

    def test_bad_supplier_pairing_falls_through_to_the_real_equivalent(self):
        def pairs(tenant_id, source_store_id, target_store_id):
            # The bad real-world row: NMA's TELMA BETA 25 paired to NMS's
            # completely unrelated EMADINE AT via a shared supplier key.
            return [("TELMA25", "1638")] if target_store_id == NMS else []

        def products(tenant_id, store_id):
            if store_id == NMS:
                return [
                    {"product_code": "1638", "product_name": "EMADINE AT", "mrp": 41.5},
                    {"product_code": "5879735", "product_name": "TELMA BETA 25MG", "mrp": 242.0},
                ]
            return []

        with patch.object(service.mapping_source_repository, "load_store_products", products), \
             patch.object(service.mapping_source_repository, "load_supplier_pairs", pairs), \
             patch.object(service.mapping_repository, "load_active_terms", lambda tenant_id: set()):
            result = service.match_cross_store_selection(
                SUPER_ADMIN_USER, TENANT, NMA, "TELMA25", "TELMA BETA 25", [NMS],
            )
        by_store = {r["store_id"]: r for r in result["results"]}
        self.assertNotEqual(by_store[NMS]["product"]["product_code"], "1638")
        self.assertEqual(by_store[NMS]["product"]["product_code"], "5879735")
        self.assertNotEqual(by_store[NMS]["match_type"], "EXACT_SUPPLIER_MATCH")

    def test_bad_supplier_pairing_with_no_real_equivalent_falls_back_to_no_match(self):
        def pairs(tenant_id, source_store_id, target_store_id):
            return [("TELMA25", "1638")] if target_store_id == NMS else []

        def products(tenant_id, store_id):
            if store_id == NMS:
                return [{"product_code": "1638", "product_name": "EMADINE AT", "mrp": 41.5}]
            return []

        with patch.object(service.mapping_source_repository, "load_store_products", products), \
             patch.object(service.mapping_source_repository, "load_supplier_pairs", pairs), \
             patch.object(service.mapping_repository, "load_active_terms", lambda tenant_id: set()):
            result = service.match_cross_store_selection(
                SUPER_ADMIN_USER, TENANT, NMA, "TELMA25", "TELMA BETA 25", [NMS],
            )
        self.assertEqual(result["results"][0]["match_type"], "NO_MATCH")
        self.assertIsNone(result["results"][0]["product"])


class TestCrossStoreSyncInputHandling(unittest.TestCase):
    def test_source_store_excluded_from_its_own_targets(self):
        by_store = _run("5886702", "BRIV 25MG  TAB", targets=[NMW, NMA])
        self.assertNotIn(NMW, by_store)
        self.assertIn(NMA, by_store)

    def test_empty_target_list_returns_no_results(self):
        result = _run("5886702", "BRIV 25MG  TAB", targets=[])
        self.assertEqual(result, {})

    def test_missing_source_name_returns_no_results(self):
        by_store = _run("5886702", None)
        self.assertEqual(by_store, {})


if __name__ == "__main__":
    unittest.main()
