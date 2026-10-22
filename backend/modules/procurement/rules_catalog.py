"""Procurement Rules Registry catalog.

Stable IDs for the owner-confirmed target and for rules that are still
unverified. This is not a second rulebook: narrative evidence stays in
docs/procurement-workspace-unification/06_PROCUREMENT_RULEBOOK.md and the
2026-10-19 audit. Unknowns stay UNVERIFIED or DECISION_REQUIRED.

Nothing here is read by decision_rules.evaluate.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from modules.procurement.quantity_profile_t import RARE_MOVING_WARNING

GROUP_CONFIRMED = "common_confirmed"
GROUP_CONFLICT = "legacy_nexora_conflict"
GROUP_STORE = "store_configurable"
GROUP_LOCKED = "locked_safety"
GROUP_UNVERIFIED = "unverified"
GROUP_APPROVAL = "approval_required"

STATUS_CONFIRMED = "CONFIRMED"
STATUS_CONFLICT = "CONFLICT_RECORDED"
STATUS_UNVERIFIED = "UNVERIFIED"
STATUS_DECISION = "DECISION_REQUIRED"
STATUS_APPROVAL = "APPROVAL_REQUIRED"

POLICY_LOCKED = "LOCKED"
POLICY_STORE = "STORE_OVERRIDE"
POLICY_NONE = "NONE"


@dataclass(frozen=True)
class RuleDef:
    rule_id: str
    name: str
    category: str
    group: str
    description: str
    source_evidence: str
    current_behavior: str
    target_behavior: str
    status: str
    value_type: str
    default_value: object
    validation: str
    override_policy: str
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: tuple | None = None

    def public(self) -> dict:
        data = asdict(self)
        if self.allowed_values is not None:
            data["allowed_values"] = list(self.allowed_values)
        return data


def _rule(**kwargs) -> RuleDef:
    return RuleDef(**kwargs)


RULES: tuple[RuleDef, ...] = (
    _rule(
        rule_id="PRR-QTY-WINDOW",
        name="Sales window",
        category="quantity",
        group=GROUP_STORE,
        description="Calendar days of sales used by the target profile.",
        source_evidence="Master prompt confirmed decisions; quantity_profile_t.WINDOW_DAYS = 90.",
        current_behavior="Legacy SQL divides by 90. Nexora evaluate receives the caller's window. This registry does not change that caller.",
        target_behavior="90 calendar days.",
        status=STATUS_CONFIRMED,
        value_type="int",
        default_value=90,
        validation="Integer from 1 to 366.",
        override_policy=POLICY_STORE,
        min_value=1,
        max_value=366,
    ),
    _rule(
        rule_id="PRR-QTY-MIN-COVER",
        name="Minimum cover",
        category="quantity",
        group=GROUP_STORE,
        description="Minimum cover days for the target profile.",
        source_evidence="Master prompt confirmed decisions; quantity_profile_t.MIN_DAYS = 13.",
        current_behavior="Legacy service default min day is 13. Nexora floors are inside evaluate and are not switched by this registry.",
        target_behavior="13 days. Must be less than or equal to maximum cover.",
        status=STATUS_CONFIRMED,
        value_type="int",
        default_value=13,
        validation="Integer from 1 to 90, and <= maximum cover.",
        override_policy=POLICY_STORE,
        min_value=1,
        max_value=90,
    ),
    _rule(
        rule_id="PRR-QTY-MAX-COVER",
        name="Maximum cover",
        category="quantity",
        group=GROUP_STORE,
        description="Maximum cover days. One input to gross demand.",
        source_evidence="Master prompt confirmed decisions; quantity_profile_t.MAX_DAYS = 18.",
        current_behavior="Legacy service default max day is 18. Live evaluate is unchanged.",
        target_behavior="18 days. Must be greater than or equal to minimum cover.",
        status=STATUS_CONFIRMED,
        value_type="int",
        default_value=18,
        validation="Integer from 1 to 180, and >= minimum cover.",
        override_policy=POLICY_STORE,
        min_value=1,
        max_value=180,
    ),
    _rule(
        rule_id="PRR-QTY-RECENCY",
        name="Valid-sale recency",
        category="quantity",
        group=GROUP_CONFLICT,
        description="Separate recency gate. Not the cover calculation.",
        source_evidence="Master prompt: 15 days. Form1.vb hard-codes DATEADD(day, -10). decision_rules.DecisionParameters.recency_days default is 10. order_local.sql uses @recencydays; uncommitted service default is 15.",
        current_behavior="Three clocks exist: VB form 10, Nexora evaluate default 10, legacy SQL parameter default 15 in the working tree. Changing the legacy default is already uncommitted work and is a behavior change risk.",
        target_behavior="15 days. A sale that fails recency stays off the auto-order list.",
        status=STATUS_CONFLICT,
        value_type="int",
        default_value=15,
        validation="Integer from 1 to 90.",
        override_policy=POLICY_STORE,
        min_value=1,
        max_value=90,
    ),
    _rule(
        rule_id="PRR-STK-SOURCE",
        name="Stock source",
        category="stock",
        group=GROUP_CONFLICT,
        description="Physical stock input for the target profile.",
        source_evidence="Master prompt: Products.TotalStock. Legacy FetchSourceData uses p.TotalStock. decision_repository load_source uses ProductTrans.StockInHand. PHASE_1_SOURCE_FIELD_MAP: OrderManagement.TotalStock is a generation-time snapshot.",
        current_behavior="Legacy order quantity uses TotalStock. Nexora evaluate uses StockInHand from its loader. Those are not the same number.",
        target_behavior="Products.TotalStock. Do not substitute StockInHand or a batch sum.",
        status=STATUS_CONFLICT,
        value_type="enum",
        default_value="Products.TotalStock",
        validation="The only allowed value is Products.TotalStock.",
        override_policy=POLICY_LOCKED,
        allowed_values=("Products.TotalStock",),
    ),
    _rule(
        rule_id="PRR-STK-PENDING",
        name="Confirmed supplier pending",
        category="stock",
        group=GROUP_UNVERIFIED,
        description="Subtract confirmed supplier pending from net demand only. Do not add it to stock for the eligibility gate.",
        source_evidence="Master prompt net formula. Phase 0 fixture accepts the number as an input. PHASE_1_SOURCE_FIELD_MAP: no pending column in the three loaders. reconciliation_rules.assignment_state remaining is not an input to suggested quantity.",
        current_behavior="Legacy SQL does not subtract pending. Nexora evaluate can add pending_receivable into available stock. No verified source column.",
        target_behavior="Subtract a confirmed pending quantity from net. The column is not chosen here.",
        status=STATUS_DECISION,
        value_type="blocked",
        default_value=None,
        validation="No value is accepted until a source column is verified. A guessed column name is rejected.",
        override_policy=POLICY_NONE,
    ),
    _rule(
        rule_id="PRR-QTY-GROSS",
        name="Gross demand",
        category="quantity",
        group=GROUP_LOCKED,
        description="Target gross demand.",
        source_evidence="Master prompt. quantity_profile_t.evaluate_profile_t uses the same four terms. Phase 0 target_formula matches it.",
        current_behavior="Legacy OrderQty uses min/max day cover and max line quantity, not max day or average bill. Nexora evaluate uses max day, max bill, and max line, and does not use average bill.",
        target_behavior="MAX(avgDailySales * maxDays, maxBillQty, maxDayQty, avgBillQty).",
        status=STATUS_CONFIRMED,
        value_type="text",
        default_value="MAX(avgDailySales * maxDays, maxBillQty, maxDayQty, avgBillQty)",
        validation="Locked text. Store override rejected.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-QTY-NET",
        name="Net demand",
        category="quantity",
        group=GROUP_LOCKED,
        description="Target net demand after physical stock and confirmed pending.",
        source_evidence="Master prompt. Pending term stays an input, not a guessed column (PRR-STK-PENDING).",
        current_behavior="Legacy uses maxqty - TotalStock. Nexora compares cover with effective available stock.",
        target_behavior="gross - Products.TotalStock - confirmedSupplierPendingQty.",
        status=STATUS_CONFIRMED,
        value_type="text",
        default_value="gross - Products.TotalStock - confirmedSupplierPendingQty",
        validation="Locked text. Store override rejected.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-QTY-SALEUNIT",
        name="SaleUnit validation",
        category="quantity",
        group=GROUP_CONFLICT,
        description="Pack size required before an automatic quantity.",
        source_evidence="Master prompt. quantity_profile_t returns BLOCKED_SALE_UNIT when SaleUnit is null or <= 0. Legacy orderable quantity is 0. Nexora evaluate falls back to loose units.",
        current_behavior="Invalid SaleUnit blocks the target and legacy orderable quantity. Nexora evaluate can still suggest loose units.",
        target_behavior="Block automatic quantity. Do not fall back to loose units.",
        status=STATUS_CONFLICT,
        value_type="bool",
        default_value=True,
        validation="Must stay true. False would allow loose-unit fallback and is rejected.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-QTY-DONTCONSIDER",
        name="DontConsiderInOrder exclusion",
        category="quantity",
        group=GROUP_CONFLICT,
        description="Exclude flagged products from target demand.",
        source_evidence="Master prompt. evaluate honors dont_consider. load_source forces the flag to 0, so the product flag is unreachable from that loader. Legacy sales CTE filters line DontConsiderInOrder = 0 and has no product-level flag.",
        current_behavior="Target and evaluate exclude when the flag is supplied. Legacy SQL can still order a product when only the product flag is set.",
        target_behavior="Exclude the product from demand calculations when the product flag is set.",
        status=STATUS_CONFLICT,
        value_type="bool",
        default_value=True,
        validation="Must stay true.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-QTY-RARE",
        name="Rare-moving product review",
        category="quantity",
        group=GROUP_LOCKED,
        description="Rare movers are a review suggestion, not an automatic order.",
        source_evidence="Master prompt rare-mover decision. quantity_profile_t reason RARE_MOVING_MANUAL_REVIEW, packs 1, auto_order false, warning text preserved. Legacy additional-row path zeros OrderQty after insert.",
        current_behavior="Legacy orderable quantity becomes 0 with status Additional. Nexora INCLUDED_RARE_MOVER_TOPUP keeps suggested quantity 1 on the include path.",
        target_behavior=(
            "Suggested quantity 1 for review. Warning: "
            + RARE_MOVING_WARNING
            + ". No automatic assignment, export, or portal order. PM must confirm. Final quantity is validated against SaleUnit before export."
        ),
        status=STATUS_CONFIRMED,
        value_type="text",
        default_value="suggested_qty=1; auto_order=false; warning=" + RARE_MOVING_WARNING,
        validation="Locked. The warning text and the no-auto-order flag cannot be overridden.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-SUP-COST",
        name="Supplier effective cost",
        category="supplier",
        group=GROUP_LOCKED,
        description="Historical received cost, not today's offer.",
        source_evidence="Master prompt supplier section. Tax basis is a separate unverified rule.",
        current_behavior="No (10*100*0.90)/12 effective-cost function was found in the 2026-10-19 audit. Ranking weights in purchaseValue.ts are mapping 100, last purchase 40, frequency 30, ptr 20, live stock 10.",
        target_behavior="Use actual received purchases within 90 days, latest six records when more than six exist, otherwise all. Include discount and free units per record. Do not apply today's offer.",
        status=STATUS_CONFIRMED,
        value_type="text",
        default_value="received_purchases_90_days; latest_six_if_more_than_six; per_record_discount_and_free",
        validation="Locked text until a later approved cost change.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-SUP-TAX-BASIS",
        name="Effective-cost tax basis",
        category="supplier",
        group=GROUP_UNVERIFIED,
        description="Whether historical cost is tax-inclusive is not verified.",
        source_evidence="Master prompt: tax basis requires source verification.",
        current_behavior="Not verified in this registry pass.",
        target_behavior="Blocked until the source column and tax treatment are verified.",
        status=STATUS_UNVERIFIED,
        value_type="blocked",
        default_value=None,
        validation="No override accepted.",
        override_policy=POLICY_NONE,
    ),
    _rule(
        rule_id="PRR-SUP-STALE",
        name="Stale price",
        category="supplier",
        group=GROUP_LOCKED,
        description="Missing recent price is a manual review, not an auto-rank.",
        source_evidence="Master prompt: show Stale Price — Manual Review and exclude from auto-ranking until verified.",
        current_behavior="Not re-checked against a single function in this pass. The target text is registered so a later worker cannot invent a silent fallback.",
        target_behavior="Show Stale Price — Manual Review and exclude from auto-ranking until verified.",
        status=STATUS_CONFIRMED,
        value_type="text",
        default_value="Stale Price — Manual Review",
        validation="Locked warning text.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-SUP-ONE",
        name="One supplier per product",
        category="supplier",
        group=GROUP_LOCKED,
        description="A product line has one supplier assignment.",
        source_evidence="Master prompt. assignment_service assigns one supplier. A second assignment must conflict.",
        current_behavior="Assignment service writes one supplier. This registry does not change that service.",
        target_behavior="Reject a second supplier assignment with a conflict response.",
        status=STATUS_CONFIRMED,
        value_type="bool",
        default_value=True,
        validation="Must stay true.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-SUP-PRECEDENCE",
        name="Assignment precedence",
        category="supplier",
        group=GROUP_LOCKED,
        description="Manual assignment wins. Auto Assign Remaining fills only unassigned lines.",
        source_evidence="Master prompt. Assignment must not silently recalculate final quantity.",
        current_behavior="Existing assignment service is the live path. This registry does not call it.",
        target_behavior="Manual assignment wins. Auto assign remaining only. Do not recalculate final quantity.",
        status=STATUS_CONFIRMED,
        value_type="text",
        default_value="manual_wins; auto_assign_remaining_unassigned_only; do_not_recalculate_qty",
        validation="Locked text.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-EXP-PRECEDENCE",
        name="Export settings precedence",
        category="export",
        group=GROUP_APPROVAL,
        description="Target chain is store+supplier, then store default, then system default.",
        source_evidence="Master prompt. procurement.supplier_export_settings is keyed by tenant_id, store_id, supplier_code only (0018_supplier_export_settings.sql). No store-default or system-default table was found.",
        current_behavior="Only the store+supplier row exists. Missing tiers are not invented in this migration.",
        target_behavior="Store + supplier, then store default, then system default, after a reviewed schema addition.",
        status=STATUS_APPROVAL,
        value_type="blocked",
        default_value=None,
        validation="No override until the missing tiers are designed and approved. Phase 8 of the audit plan already records this dependency.",
        override_policy=POLICY_NONE,
    ),
    _rule(
        rule_id="PRR-RCV-NOT-SUPPLIED",
        name="Receipt, pending, and Not Supplied",
        category="receipt",
        group=GROUP_UNVERIFIED,
        description="Not Supplied and pending closure are not given a new formula here.",
        source_evidence="reconciliation_rules.assignment_state: remaining = max(0, assigned - received). That remaining is not suggested quantity. Master prompt Phase 10 describes pending and Not Supplied; this pass did not re-trace every receipt writer.",
        current_behavior="Remaining quantity is derived from assigned minus received. A distinct Not Supplied decision column was not confirmed here.",
        target_behavior="Leave unverified. Do not invent a Not Supplied status or a pending release rule.",
        status=STATUS_UNVERIFIED,
        value_type="blocked",
        default_value=None,
        validation="No override accepted.",
        override_policy=POLICY_NONE,
    ),
    _rule(
        rule_id="PRR-PERM-ROLE",
        name="Legacy role mapping",
        category="permission",
        group=GROUP_UNVERIFIED,
        description="VB Users.Role is an integer. Do not map 1 to Admin or 2 to PM.",
        source_evidence="LoginForm.vb and UserSession.vb. Master prompt Phase 12. PHASE_1_SOURCE_FIELD_MAP left Role 1/2 unmapped.",
        current_behavior="Nexora platform capabilities are separate from the VB role integer.",
        target_behavior="Blocked until the owner maps the integers.",
        status=STATUS_DECISION,
        value_type="blocked",
        default_value=None,
        validation="No override accepted.",
        override_policy=POLICY_NONE,
    ),
    _rule(
        rule_id="PRR-PERM-SNAPSHOT",
        name="Effective-rule snapshot",
        category="permission",
        group=GROUP_LOCKED,
        description="A new refresh can store the rule set it used. Later edits do not rewrite that snapshot.",
        source_evidence="procurement_refreshes already stores rolling_days, min_days, and max_days. Those three columns cannot store the full effective set. OrderHeaderDetails is not extended.",
        current_behavior="Live refresh generation does not read this registry. Existing refreshes keep a null rule_snapshot_id until a later approved writer is added.",
        target_behavior="Future refreshes may attach a snapshot id. Confirmed or exported orders are not recalculated when rules change.",
        status=STATUS_CONFIRMED,
        value_type="text",
        default_value="future_refresh_only",
        validation="Locked. Value cannot be changed to retroactive.",
        override_policy=POLICY_LOCKED,
    ),
    _rule(
        rule_id="PRR-SAFE-TXNVALIDITY",
        name="Transaction validity",
        category="safety",
        group=GROUP_UNVERIFIED,
        description="transactionvalidity = 0 is the inclusion filter. Cancelled versus modified is not mapped.",
        source_evidence="Master prompt: do not invent the mapping. Phase 0 and Phase 1 both left it unknown.",
        current_behavior="Sales SQL keeps transactionvalidity = 0. The meaning of other values is unknown.",
        target_behavior="Remain blocked. Do not add a configurable map.",
        status=STATUS_UNVERIFIED,
        value_type="blocked",
        default_value=None,
        validation="No override accepted.",
        override_policy=POLICY_NONE,
    ),
    _rule(
        rule_id="PRR-SAFE-PROFILE",
        name="Profile T rollout",
        category="safety",
        group=GROUP_APPROVAL,
        description="Profile T is implemented and tested. It is not the live engine.",
        source_evidence="quantity_profile_t.py is not called by decision_rules.evaluate. Phase 0 comparison passed. Master prompt requires an explicit store-level cutover before the default changes.",
        current_behavior="Live Purchase Manager still uses decision_rules.evaluate.",
        target_behavior="Stay disabled until the comparison gate and an explicit rollout approval.",
        status=STATUS_APPROVAL,
        value_type="bool",
        default_value=False,
        validation="Must stay false. A store cannot turn Profile T on from this screen.",
        override_policy=POLICY_LOCKED,
    ),
)

BY_ID = {rule.rule_id: rule for rule in RULES}


def require_rule(rule_id: str) -> RuleDef:
    try:
        return BY_ID[rule_id]
    except KeyError as exc:
        raise KeyError(rule_id) from exc
