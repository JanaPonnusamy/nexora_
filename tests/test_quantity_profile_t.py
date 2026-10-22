"""P1-A. Profile T matches the Phase 0 target_formula on every fixture case.

Does not call decision_rules.evaluate and does not open a database.
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_REPO_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from modules.procurement.quantity_profile_t import (  # noqa: E402
    RARE_MOVING_WARNING,
    evaluate_profile_t,
)

from procurement_formula_compare import AS_OF, cases, target_formula  # noqa: E402


def test_profile_t_matches_phase0_target_on_every_case():
    for case in cases():
        expected = target_formula(case)
        actual = evaluate_profile_t(case, AS_OF)
        assert actual["reason"] == expected["reason"], case["name"]
        assert actual["packs"] == expected["packs"], case["name"]
        assert actual["auto_order"] == expected["auto_order"], case["name"]
        if expected["reason"] == "RARE_MOVING_MANUAL_REVIEW":
            assert actual["warning"] == RARE_MOVING_WARNING
            assert actual["auto_order"] is False
        else:
            assert actual["warning"] is None


def test_profile_t_spike_and_pending_numbers():
    by_name = {case["name"]: case for case in cases()}
    spike = evaluate_profile_t(by_name["spike_day_bill"], AS_OF)
    assert spike["packs"] == 5 and spike["auto_order"] is True
    pending = evaluate_profile_t(by_name["pending_20"], AS_OF)
    assert pending["packs"] == 3 and pending["reason"] == "AUTO"
    blocked = evaluate_profile_t(by_name["sale_unit_null"], AS_OF)
    assert blocked["packs"] is None and blocked["reason"] == "BLOCKED_SALE_UNIT"
