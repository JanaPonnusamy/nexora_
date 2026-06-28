---
module: Procurement
version: 0.2
status: Active
owner: Solution Architecture
updated: 2026-06-27
---

# NEXORA Platform — Procurement Business Rule Catalogue

> **This is the canonical business-rule catalogue for Procurement.** Every procurement rule is
> documented here **independently** and is the authoritative source for future stored procedures,
> APIs, UI behaviour and automated testing. The Functional Design Document
> (`Procurement_Business_Architecture_Specification.md`) describes the *narrative*; this catalogue
> holds the *atomic, testable rules*; the **execution order** is defined separately in
> `docs/Procurement_Decision_Flow.md`.
>
> Built **incrementally** as topics are analysed. Code is evidence only; rules are the design.

## How to read a rule

Each rule uses this structure:

- **Rule ID** · **Rule Name** · **Purpose** · **Business Description** · **Inputs**
- **Calculation Logic** — formula/steps (`N/A` for non-computational rules).
- **Conditions** · **Exceptions** · **Dependencies** · **Outputs**
- **Business Example** — a realistic scenario.
- **Worked Calculation** — that example computed step by step.
- **Intermediate Values** — the named interim numbers.
- **Final Decision** — the resulting outcome for the example.
- **Reason Code** — controlled-vocabulary code stored on the decision (see PR-BR-015).
- **Displayed Explanation** — human-readable text shown to the Purchase Manager.
- **Decision Explorer Output** — what the future Procurement Decision Explorer surfaces.
- **Future Decision Dependencies** — later rules/topics that consume or modify this output.
- **Legacy Evidence** · **Status** · **Version**

> **Explainability is mandatory** (FDD §8.17). Every evaluated product stores a **Reason Code** + **Reason
> Text**; excluded products are recorded too (not silently dropped). Reason Codes are defined in **PR-BR-015**.

## ID allocation

| Range | Domain |
|-------|--------|
| `PR-BR-001` … `PR-BR-016` | **Decision Engine** rules. |
| `PR-BR-017` … `PR-BR-025` | **Governance, Access & Sync Orchestration**. |
| `PR-BR-026` … `PR-BR-035` | **Customer Demand** (Topic 04). |
| `PR-BR-036` … | Pending, Supplier Assignment, GRN (Topics 05–07). |

## Rule register (index)

| ID | Name | Domain | Status |
|----|------|--------|--------|
| PR-BR-001 | Rolling Sales Window & Eligibility | Decision Engine | Ratified |
| PR-BR-002 | Average Daily Sales | Decision Engine | Ratified |
| PR-BR-003 | Days Cover | Decision Engine | Ratified |
| PR-BR-004 | Min-Days Reorder Trigger | Decision Engine | Ratified |
| PR-BR-005 | Max-Days Target Stock | Decision Engine | Ratified |
| PR-BR-006 | Coverage Required Quantity | Decision Engine | Ratified |
| PR-BR-007 | Max-Day-Sale Protection Floor | Decision Engine | Ratified |
| PR-BR-008 | Max-Bill-Quantity Protection Floor | Decision Engine | Ratified |
| PR-BR-009 | Final Required Quantity | Decision Engine | Ratified |
| PR-BR-010 | Movement Class | Decision Engine | Ratified |
| PR-BR-011 | Stock Status | Decision Engine | Ratified |
| PR-BR-012 | Sales Behaviour Metrics | Decision Engine | Analysed |
| PR-BR-013 | Order-Exclusion Flag | Decision Engine | Analysed |
| PR-BR-014 | Effective Available | Decision Engine | Ratified |
| PR-BR-015 | Reason Code & Explainability | Decision Engine | Ratified |
| PR-BR-016 | Configurable Decision Parameters | Decision Engine | Ratified |
| PR-BR-017 | Role-Based Procurement Access | Access | Ratified |
| PR-BR-018 | Purchase Manager Responsibilities | Access | Ratified |
| PR-BR-019 | Business Cycle Administration | Access | Ratified |
| PR-BR-020 | Refresh Administration | Access | Ratified |
| PR-BR-021 | Automatic Synchronization Before Refresh | Sync Orchestration | Ratified |
| PR-BR-022 | Business Cycle Creation Workflow | Sync Orchestration | Ratified |
| PR-BR-023 | Store Completion Notification | Sync Orchestration | Ratified |
| PR-BR-024 | Automatic Store Synchronization | Sync Orchestration | Ratified |
| PR-BR-025 | Synchronization Visibility | Sync Orchestration | Ratified |
| PR-BR-026 | Customer Demand Entity & Mandatory Fields | Customer Demand | Ratified |
| PR-BR-027 | Demand Status Model & Lifecycle | Customer Demand | Ratified |
| PR-BR-028 | Demand Priority | Customer Demand | Ratified |
| PR-BR-029 | Demand Type / Origin | Customer Demand | Ratified |
| PR-BR-030 | Customer History | Customer Demand | Ratified |
| PR-BR-031 | Duplicate Active Demand Validation | Customer Demand | Ratified |
| PR-BR-032 | Demand Explainability | Customer Demand | Ratified |
| PR-BR-033 | Demand → Procurement Traceability | Customer Demand | Ratified |
| PR-BR-034 | Demand Decision Explorer (not converted) | Customer Demand | Ratified |
| PR-BR-035 | Customer Product Match | Customer Demand | Analysed |

> **Running example (used across Decision Engine rules):** Store "Main"; product PARA-500;
> Rolling Days = 90; Refresh Min Days = 10, Max Days = 20. In the 90-day window: 900 units sold,
> biggest single day 40, biggest single bill 60, 120 bills. Current Stock = 30; Pending Receivable = 50;
> Confirmed In Transit = 0; Reserved = 10. *(Approved corrections of 2026-06-27 are reflected throughout.)*

---

# Domain: Decision Engine

> **Legacy evidence base:** OrderNMC `nx_sp_GetProductProcurementMetrics` (metrics) and
> `nx_sp_BuildVirtualProductList` (decision); VB.NET `Form1.vb`. **Approved corrections (2026-06-27):**
> (1) use cycle **Rolling Days** (default 90, configurable) — never a hard-coded 30; (2) Max-Bill/Max-Day
> are **minimum protection floors**, not caps; (3) size against **Effective Available**, not raw stock;
> (4) thresholds are **configurable parameters**; (5) every decision stores **Reason Code + Reason Text**.

## PR-BR-001 — Rolling Sales Window & Eligibility

- **Purpose:** Define which sales count toward metrics and over what window.
- **Business Description:** Metrics use a trailing **Rolling Days** window of **valid, order-eligible** sales
  of **active products**. Rolling Days comes from the **Business Cycle** (default 90, configurable) — never
  hard-coded.
- **Inputs:** `ProductSaleInformation` (Quantity, BillNumber, TransactionDate, `TransactionValidity`,
  `DontConsiderInOrder`); `Products.IsActive`; **Rolling Days (cycle parameter, PR-BR-016)**.
- **Calculation Logic:** Include a sale iff `TransactionValidity=0 AND DontConsiderInOrder=0 AND
  TransactionDate >= today − RollingDays`; product `IsActive=1`.
- **Conditions:** Every Refresh metrics pass, per store.
- **Exceptions:** Invalid/flagged sales and inactive products excluded (PR-BR-013).
- **Dependencies:** PR-BR-016 (Rolling Days); feeds PR-BR-002, 012.
- **Outputs:** Eligible sales set per product.
- **Business Example:** PARA-500 over the last 90 days.
- **Worked Calculation:** Window = today−90d; include the 900 valid units across 120 bills.
- **Intermediate Values:** WindowQty = 900; Bills = 120.
- **Final Decision:** PARA-500 is eligible (active, has valid sales).
- **Reason Code:** `WINDOW_ELIGIBLE`.
- **Displayed Explanation:** "Using last 90 days of valid sales (cycle Rolling Days)."
- **Decision Explorer Output:** Window length, included/excluded sale counts, exclusions applied.
- **Future Decision Dependencies:** All metrics (PR-BR-002/012) and every downstream quantity rule.
- **Legacy Evidence:** `nx_sp_GetProductProcurementMetrics` WHERE clause. **Corrected:** legacy hard-coded
  30 days → now cycle Rolling Days (90).
- **Status:** Ratified · **Version:** 2.0

## PR-BR-002 — Average Daily Sales

- **Purpose:** Establish the per-day demand baseline.
- **Business Description:** Average quantity sold per day across the rolling window.
- **Inputs:** Eligible window sales (PR-BR-001); Rolling Days.
- **Calculation Logic:** `AvgDailySales = WindowQty / RollingDays` (full window length, not days-with-sales).
- **Conditions:** Per product per Refresh.
- **Exceptions:** No eligible sales → `AvgDailySales = 0` (→ ineligible, PR-BR-004).
- **Dependencies:** PR-BR-001; drives PR-BR-003, 005, 010.
- **Outputs:** `AvgDailySales`.
- **Business Example:** PARA-500.
- **Worked Calculation:** `900 / 90 = 10`.
- **Intermediate Values:** AvgDailySales = 10/day.
- **Final Decision:** Baseline 10 units/day.
- **Reason Code:** `BASELINE_COMPUTED`.
- **Displayed Explanation:** "Sells about 10/day over 90 days."
- **Decision Explorer Output:** WindowQty, RollingDays, AvgDailySales.
- **Future Decision Dependencies:** PR-BR-003 (cover), 005 (target), 010 (movement class).
- **Legacy Evidence:** `SUM(Quantity)/@RollingDays`.
- **Status:** Ratified · **Version:** 2.0

## PR-BR-003 — Days Cover

- **Purpose:** Express how long stock lasts at the current rate.
- **Business Description:** Stock measured in days of forward cover, using Effective Available
  (PR-BR-014) for an accurate position.
- **Inputs:** Effective Available (PR-BR-014); `AvgDailySales` (PR-BR-002).
- **Calculation Logic:** `DaysCover = EffectiveAvailable / AvgDailySales` (`0` if avg ≤ 0). *(Legacy used
  raw CurrentStock; corrected to Effective Available.)*
- **Conditions:** Per product per Refresh.
- **Exceptions:** Non-selling → 0.
- **Dependencies:** PR-BR-002, 014; drives PR-BR-004, 011.
- **Outputs:** `DaysCover`.
- **Business Example:** PARA-500: EffectiveAvailable = 70 (see PR-BR-014), avg 10.
- **Worked Calculation:** `70 / 10 = 7` days.
- **Intermediate Values:** DaysCover = 7.
- **Final Decision:** 7 days of cover.
- **Reason Code:** `COVER_COMPUTED`.
- **Displayed Explanation:** "About 7 days of stock left (incl. incoming)."
- **Decision Explorer Output:** EffectiveAvailable, AvgDailySales, DaysCover.
- **Future Decision Dependencies:** PR-BR-004 (trigger), 011 (status).
- **Legacy Evidence:** `DaysCover` CASE (used raw stock; corrected).
- **Status:** Ratified · **Version:** 2.0

## PR-BR-004 — Min-Days Reorder Trigger

- **Purpose:** Decide which products need procuring (inclusion/exclusion).
- **Business Description:** A product is a candidate only if it is **selling** and cover is **below Min Days**.
- **Inputs:** `AvgDailySales` (PR-BR-002); `DaysCover` (PR-BR-003); `MinDays` (Refresh).
- **Calculation Logic:** Include iff `AvgDailySales > 0 AND DaysCover < MinDays`; else exclude.
- **Conditions:** Decision pass of each Refresh.
- **Exceptions:** Non-selling never included (no speculative buying).
- **Dependencies:** Min Days per Refresh (D4); PR-BR-002/003.
- **Outputs:** Candidate set; inclusion/exclusion Reason Code per product.
- **Business Example:** PARA-500: cover 7, MinDays 10.
- **Worked Calculation:** `7 < 10` and `avg 10 > 0` → include.
- **Intermediate Values:** trigger = TRUE.
- **Final Decision:** **Included** for procurement.
- **Reason Code:** include → `INCLUDED_BELOW_MIN_DAYS`; exclude → `EXCLUDED_ADEQUATE_COVER` /
  `EXCLUDED_NOT_SELLING`.
- **Displayed Explanation:** "Included: 7 days cover is below the 10-day minimum."
- **Decision Explorer Output:** Why included/excluded; MinDays, DaysCover, AvgDailySales.
- **Future Decision Dependencies:** PR-BR-005..009 (sizing) only run for included products.
- **Legacy Evidence:** `WHERE AvgDailySales>0 AND DaysCover<@MinDays`.
- **Status:** Ratified · **Version:** 2.0

## PR-BR-005 — Max-Days Target Stock

- **Purpose:** Define the coverage target (how much cover to restore to).
- **Business Description:** Target stock = Max-Days of forward demand.
- **Inputs:** `AvgDailySales`; `MaxDays` (Refresh).
- **Calculation Logic:** `TargetStockQty = AvgDailySales × MaxDays`.
- **Conditions:** Per candidate.
- **Exceptions:** Validation `MaxDays ≥ MinDays > 0` at refresh creation.
- **Dependencies:** Max Days per Refresh (D4); PR-BR-002.
- **Outputs:** `TargetStockQty`.
- **Business Example:** PARA-500: avg 10, MaxDays 20.
- **Worked Calculation:** `10 × 20 = 200`.
- **Intermediate Values:** TargetStockQty = 200.
- **Final Decision:** Restore cover to 200 units.
- **Reason Code:** `TARGET_COMPUTED`.
- **Displayed Explanation:** "Target stock = 20 days × 10/day = 200."
- **Decision Explorer Output:** AvgDailySales, MaxDays, TargetStockQty.
- **Future Decision Dependencies:** PR-BR-006 (coverage required).
- **Legacy Evidence:** `AvgDailySales * @MaxDays`.
- **Status:** Ratified · **Version:** 2.0

## PR-BR-006 — Coverage Required Quantity

- **Purpose:** Base order quantity from coverage, before protection floors and rounding.
- **Business Description:** Gap between target stock and **Effective Available** (not raw stock).
- **Inputs:** `TargetStockQty` (PR-BR-005); **Effective Available** (PR-BR-014).
- **Calculation Logic:** `CoverageRequired = TargetStockQty − EffectiveAvailable`. *(Replaces legacy
  `Target − CurrentStock`.)*
- **Conditions:** Per candidate.
- **Exceptions:** May be ≤ 0 if already covered → handled by PR-BR-009.
- **Dependencies:** PR-BR-005, 014.
- **Outputs:** `CoverageRequired`.
- **Business Example:** PARA-500: target 200, EffectiveAvailable 70.
- **Worked Calculation:** `200 − 70 = 130`.
- **Intermediate Values:** CoverageRequired = 130.
- **Final Decision:** Need 130 from coverage (before protection).
- **Reason Code:** `COVERAGE`.
- **Displayed Explanation:** "Need 130 to reach the 200-unit target (after counting incoming/reserved)."
- **Decision Explorer Output:** TargetStockQty, EffectiveAvailable, CoverageRequired.
- **Future Decision Dependencies:** PR-BR-007/008 (floors), 009 (final).
- **Legacy Evidence:** `(AvgDailySales*@MaxDays) − CurrentStock`. **Corrected** to Effective Available.
- **Status:** Ratified · **Version:** 2.0

## PR-BR-007 — Max-Day-Sale Protection Floor

- **Purpose:** Ensure the order covers a repeat of the largest single-day demand.
- **Business Description:** **Maximum Day Sale Quantity is a minimum protection quantity (a FLOOR), not a
  cap.** The required quantity is raised up to it.
- **Inputs:** `CoverageRequired` (PR-BR-006); `MaxDaySaleQty` (PR-BR-012).
- **Calculation Logic:** `Required = MAX(CoverageRequired, MaxDaySaleQty)`.
- **Conditions:** Per candidate, after coverage.
- **Exceptions:** No effect if coverage already ≥ MaxDaySaleQty.
- **Dependencies:** PR-BR-006, 012.
- **Outputs:** `Required`; determining reason if it raised the value.
- **Business Example:** PARA-500: coverage 130, MaxDaySale 40.
- **Worked Calculation:** `MAX(130, 40) = 130` (no change).
- **Intermediate Values:** Required = 130.
- **Final Decision:** Floor not binding here.
- **Reason Code:** binding → `SPIKE_PROTECTION` (else unchanged).
- **Displayed Explanation:** "Order at least the biggest single-day sale (40)." (not binding in example)
- **Decision Explorer Output:** CoverageRequired, MaxDaySaleQty, whether floor was binding.
- **Future Decision Dependencies:** PR-BR-008, 009.
- **Legacy Evidence:** `SET RawRequiredQty = MaxDaySaleQty WHERE Raw < MaxDaySaleQty`. **Corrected** FDD
  wording (was "cap").
- **Status:** Ratified · **Version:** 2.0

## PR-BR-008 — Max-Bill-Quantity Protection Floor

- **Purpose:** Ensure the order covers a repeat of the largest single bill.
- **Business Description:** **Maximum Bill Quantity is a minimum protection quantity (a FLOOR), not a cap.**
  Applied after PR-BR-007.
- **Inputs:** `Required` (post PR-BR-007); `MaxBillQty` (PR-BR-012).
- **Calculation Logic:** `Required = MAX(Required, MaxBillQty)`.
- **Conditions:** Per candidate, after spike floor.
- **Exceptions:** No effect if already ≥ MaxBillQty.
- **Dependencies:** PR-BR-007, 012.
- **Outputs:** `Required`; determining reason if binding.
- **Business Example:** PARA-500: required 130, MaxBill 60.
- **Worked Calculation:** `MAX(130, 60) = 130` (not binding).
- **Intermediate Values:** Required = 130.
- **Final Decision:** Floor not binding here.
- **Reason Code:** binding → `MAX_BILL_TRIGGER` (else unchanged).
- **Displayed Explanation:** "Order at least the biggest single bill (60)." (not binding in example)
- **Decision Explorer Output:** Required-before, MaxBillQty, whether binding.
- **Future Decision Dependencies:** PR-BR-009.
- **Legacy Evidence:** `SET RawRequiredQty = MaxBillQty WHERE Raw < MaxBillQty`. **Corrected** FDD wording.
- **Status:** Ratified · **Version:** 2.0

## PR-BR-009 — Final Required Quantity

- **Purpose:** Produce the integer suggested order quantity and its determining reason.
- **Business Description:** Take the **maximum applicable** of coverage and protection floors, round up,
  and discard non-orders. Records which rule determined the final quantity.
- **Inputs:** `CoverageRequired`, `MaxDaySaleQty`, `MaxBillQty`.
- **Calculation Logic:** `Required = MAX(CoverageRequired, MaxDaySaleQty, MaxBillQty)`;
  `FinalRequiredQty = CEILING(Required)`; drop if `≤ 0`. **Determining reason** = the argument that equals
  the MAX (`COVERAGE` | `SPIKE_PROTECTION` | `MAX_BILL_TRIGGER`).
- **Conditions:** Per candidate.
- **Exceptions:** `Final ≤ 0` → excluded (`EXCLUDED_ZERO_REQUIRED`).
- **Dependencies:** PR-BR-006/007/008.
- **Outputs:** `final_required_qty`; determining Reason Code + Text → `order_virtual_items`.
- **Business Example:** PARA-500.
- **Worked Calculation:** `MAX(130, 40, 60) = 130` → `CEILING(130) = 130`.
- **Intermediate Values:** Required = 130; determinant = COVERAGE.
- **Final Decision:** **Suggested order = 130 units.**
- **Reason Code:** `COVERAGE` (this example).
- **Displayed Explanation:** "Suggested 130 — driven by coverage to the 200 target; protection floors (40, 60) not binding."
- **Decision Explorer Output:** All three candidates, the MAX, the determinant, final qty.
- **Future Decision Dependencies:** Customer Demand (PR-BR-026+, additive), Manual Override, Supplier
  Assignment (Topic 06).
- **Legacy Evidence:** `CEILING(...)` + `DELETE WHERE FinalRequiredQty<=0`.
- **Status:** Ratified · **Version:** 2.0

## PR-BR-010 — Movement Class

- **Purpose:** Classify products by sales velocity.
- **Business Description:** Bucket by average daily sales, using **configurable** cut-offs (PR-BR-016).
- **Inputs:** `AvgDailySales`; Movement cut-offs (Fast/Medium/Slow).
- **Calculation Logic:** `FAST` if `≥ fast_cut`; `MEDIUM` if `≥ medium_cut`; `SLOW` if `> 0`; else `NONMOVING`.
  Defaults: fast 50, medium 10.
- **Conditions:** Per product per Refresh.
- **Exceptions:** None.
- **Dependencies:** PR-BR-002, 016.
- **Outputs:** `MovementClass`.
- **Business Example:** PARA-500: avg 10, defaults.
- **Worked Calculation:** `10 ≥ 10` → MEDIUM.
- **Intermediate Values:** MovementClass = MEDIUM.
- **Final Decision:** Classified MEDIUM.
- **Reason Code:** `MOVEMENT_MEDIUM` (et al.).
- **Displayed Explanation:** "Medium mover (~10/day)."
- **Decision Explorer Output:** AvgDailySales, cut-offs used, class.
- **Future Decision Dependencies:** Workspace prioritisation; Monthly-Once-Sold handling.
- **Legacy Evidence:** `MovementClass` CASE. **Corrected:** thresholds now configurable.
- **Status:** Ratified · **Version:** 2.0

## PR-BR-011 — Stock Status

- **Purpose:** Flag urgency of a product's stock position.
- **Business Description:** Classify by days of cover / on-hand, using **configurable** cut-offs (PR-BR-016).
- **Inputs:** Effective Available; `DaysCover` (PR-BR-003); Low/Safe cut-offs.
- **Calculation Logic:** `OUT` if available ≤ 0; `LOW` if cover < `low_cut`; `SAFE` if cover ≤ `safe_cut`;
  else `OVERSTOCK`. Defaults: low 3, safe 15.
- **Conditions:** Per product per Refresh.
- **Exceptions:** None.
- **Dependencies:** PR-BR-003, 014, 016.
- **Outputs:** `StockStatus` (feeds High-Priority routing, Topic 02).
- **Business Example:** PARA-500: cover 7, defaults.
- **Worked Calculation:** `7 ≥ 3` and `7 ≤ 15` → SAFE.
- **Intermediate Values:** StockStatus = SAFE.
- **Final Decision:** SAFE.
- **Reason Code:** `STATUS_SAFE` (et al.).
- **Displayed Explanation:** "Stock SAFE (7 days)."
- **Decision Explorer Output:** DaysCover, cut-offs, status.
- **Future Decision Dependencies:** Workspace section/priority (Topic 02).
- **Legacy Evidence:** `StockStatus` CASE. **Corrected:** thresholds now configurable.
- **Status:** Ratified · **Version:** 2.0

## PR-BR-012 — Sales Behaviour Metrics

- **Purpose:** Provide demand statistics used by sizing and classification.
- **Business Description:** Per-product window statistics.
- **Inputs:** Eligible window sales (PR-BR-001).
- **Calculation Logic:** `MaxDaySaleQty = MAX(daily total)`; `MaxBillQty = MAX(per-bill total)`;
  `WindowSalesQty = SUM(Quantity)`; `BillingFrequency = COUNT(DISTINCT BillNumber)`.
- **Conditions:** Per product per Refresh.
- **Exceptions:** Zero when no eligible sales.
- **Dependencies:** PR-BR-001; feeds PR-BR-007/008.
- **Outputs:** `MaxDaySaleQty`, `MaxBillQty`, `WindowSalesQty`, `BillingFrequency`.
- **Business Example:** PARA-500 window.
- **Worked Calculation:** biggest day 40; biggest bill 60; total 900; bills 120.
- **Intermediate Values:** as above.
- **Final Decision:** Metrics published for the product.
- **Reason Code:** `METRICS_COMPUTED`.
- **Displayed Explanation:** "Peak day 40, peak bill 60, 120 bills in 90 days."
- **Decision Explorer Output:** the four metrics with their source aggregates.
- **Future Decision Dependencies:** PR-BR-007/008 floors; Monthly-Once-Sold (BillingFrequency).
- **Legacy Evidence:** `#SalesMetrics` aggregates.
- **Status:** Analysed · **Version:** 1.1

## PR-BR-013 — Order-Exclusion Flag

- **Purpose:** Let the business hold specific items/sales out of procurement.
- **Business Description:** `DontConsiderInOrder` sales, invalid sales (`TransactionValidity≠0`), and
  inactive products (`IsActive≠1`) are excluded.
- **Inputs:** `ProductSaleInformation.DontConsiderInOrder`, `.TransactionValidity`; `Products.IsActive`.
- **Calculation Logic:** Boolean exclusion filter (see PR-BR-001).
- **Conditions:** Always, during metrics.
- **Exceptions:** None — exclusion is absolute.
- **Dependencies:** PR-BR-001.
- **Outputs:** Reduced eligible set; exclusion Reason Code per product.
- **Business Example:** A consignment SKU flagged `DontConsiderInOrder=1`.
- **Worked Calculation:** flag = 1 → removed from window.
- **Intermediate Values:** eligible = FALSE.
- **Final Decision:** **Excluded** from the Workspace.
- **Reason Code:** `EXCLUDED_FLAGGED` / `EXCLUDED_INACTIVE`.
- **Displayed Explanation:** "Excluded: marked 'do not order'."
- **Decision Explorer Output:** which flag caused exclusion.
- **Future Decision Dependencies:** none (terminal exclusion).
- **Legacy Evidence:** WHERE filters in metrics SP.
- **Status:** Analysed · **Version:** 1.1

## PR-BR-014 — Effective Available

- **Purpose:** Size orders against the true available position, not raw stock — avoid double-ordering.
- **Business Description:** The stock position effectively available to satisfy future demand, combining
  on-hand, incoming and committed-out quantities. **Replaces "current stock" in coverage and cover.**
- **Inputs:** Current Stock; Pending Receivable; Confirmed In Transit; Reserved Quantity.
- **Calculation Logic:**
  `EffectiveAvailable = CurrentStock + PendingReceivable + ConfirmedInTransit − ReservedQuantity`.
  (Incoming adds; reserved/committed-out subtracts. Component sourcing finalised in Topic 05.)
- **Conditions:** Per product per Refresh, before PR-BR-003 and PR-BR-006.
- **Exceptions:** Negative result is floored at 0 for cover purposes (assumption — confirm in Topic 05).
- **Dependencies:** Topic 05 (Pending) for component definitions; used by PR-BR-003, 006.
- **Outputs:** `EffectiveAvailable`.
- **Business Example:** PARA-500: stock 30, pending receivable 50, in transit 0, reserved 10.
- **Worked Calculation:** `30 + 50 + 0 − 10 = 70`.
- **Intermediate Values:** EffectiveAvailable = 70.
- **Final Decision:** Treat 70 as available when sizing.
- **Reason Code:** `EFFECTIVE_AVAILABLE_COMPUTED`.
- **Displayed Explanation:** "Available 70 = 30 on hand + 50 incoming − 10 reserved."
- **Decision Explorer Output:** the four components and the total.
- **Future Decision Dependencies:** Pending (Topic 05), Partial Receipt, GRN reconciliation (Topic 07).
- **Legacy Evidence:** Approved decision (non-legacy). Legacy engine used **raw CurrentStock only** —
  **superseded**.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-015 — Reason Code & Explainability

- **Purpose:** Make every decision explainable and queryable by the Procurement Decision Explorer.
- **Business Description:** Every product evaluated in a Refresh persists an **inclusion/exclusion Reason
  Code**, a **final-quantity determining Reason Code**, and a **Reason Text**. **Excluded products are
  stored too** (not silently dropped), so exclusions are explainable.
- **Inputs:** Outputs of PR-BR-001…014 (the rule trace).
- **Calculation Logic:** N/A (recording rule). Controlled vocabulary:
  - *Inclusion:* `INCLUDED_BELOW_MIN_DAYS`.
  - *Exclusion:* `EXCLUDED_NOT_SELLING`, `EXCLUDED_ADEQUATE_COVER`, `EXCLUDED_FLAGGED`,
    `EXCLUDED_INACTIVE`, `EXCLUDED_ZERO_REQUIRED`.
  - *Final-quantity determinant:* `COVERAGE`, `SPIKE_PROTECTION`, `MAX_BILL_TRIGGER`.
- **Conditions:** For every product, every Refresh.
- **Exceptions:** None — explainability is mandatory (FDD §8.17).
- **Dependencies:** All engine rules; the Decision Flow document (execution order).
- **Outputs:** `reason_code`, `quantity_reason_code`, `reason_text` on each evaluated product.
- **Business Example:** PARA-500.
- **Worked Calculation:** included (cover 7 < 10); final 130 by MAX(130,40,60)=coverage.
- **Intermediate Values:** reason_code=`INCLUDED_BELOW_MIN_DAYS`; quantity_reason_code=`COVERAGE`.
- **Final Decision:** "Included; 130 units; driven by COVERAGE."
- **Reason Code:** *(this rule defines the vocabulary).*
- **Displayed Explanation:** "Why included, why this quantity, which rule decided it."
- **Decision Explorer Output:** Answers "Why included?/Why excluded?/Which rules evaluated?/Which rule set
  the quantity?" for any product.
- **Future Decision Dependencies:** Customer Demand, Pending, Override, Supplier reason codes (extend the
  vocabulary in later topics).
- **Legacy Evidence:** Approved decision (non-legacy). Legacy stored only `trigger_reason`
  (`SPIKE_PROTECTION`/`MAX_BILL_TRIGGER`) and **dropped excluded rows** — superseded.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-016 — Configurable Decision Parameters

- **Purpose:** Remove all hard-coded thresholds; make the engine tunable per business.
- **Business Description:** Every decision threshold is a **configurable platform parameter** governed by
  `procurement.rules.manage` — never a literal constant.
- **Inputs:** Parameter store (cycle/refresh/platform scope).
- **Calculation Logic:** N/A (configuration rule). Parameters:
  | Parameter | Scope | Default |
  |-----------|-------|---------|
  | Rolling Days | Business Cycle | 90 |
  | Min Days | Refresh | — |
  | Max Days | Refresh | — |
  | Movement Fast / Medium cut-offs | Platform/store | 50 / 10 |
  | Stock Low / Safe cover cut-offs | Platform/store | 3 / 15 |
- **Conditions:** Read at Refresh generation; applied across PR-BR-001/004/005/010/011.
- **Exceptions:** Missing parameter → use documented default.
- **Dependencies:** Rule-management permission; PR-BR-001/010/011.
- **Outputs:** Effective parameter set for the Refresh (recorded for explainability).
- **Business Example:** Store "Main" sets Rolling Days 90, Min 10, Max 20.
- **Worked Calculation:** N/A.
- **Intermediate Values:** N/A.
- **Final Decision:** Engine runs with the configured parameters.
- **Reason Code:** `PARAMS_APPLIED`.
- **Displayed Explanation:** "Calculated with Rolling 90, Min 10, Max 20, default classification cut-offs."
- **Decision Explorer Output:** the exact parameter values used for the Refresh.
- **Future Decision Dependencies:** all engine rules.
- **Legacy Evidence:** Approved decision (non-legacy). Legacy hard-coded 30 / 50 / 10 / 3 / 15 — superseded.
- **Status:** Ratified · **Version:** 1.0

---

# Domain: Governance, Access & Sync Orchestration

> These rules are authorization/orchestration gates; their quantitative fields (Worked Calculation,
> Intermediate Values) are `N/A`. The mandatory explainability fields are summarised in the
> **Explainability addendum** table at the end of this domain; full narrative is in FDD §3.4–3.6.

## PR-BR-017 — Role-Based Procurement Access

- **Purpose:** Restrict procurement to authorized users only.
- **Business Description:** Procurement is a restricted module on the Nexora Platform RBAC. Users without
  `procurement.workspace.view` never see the Workspace. Procurement defines **no roles of its own** —
  access is by **permission** (AC-01, AC-03).
- **Inputs:** Authenticated user; platform role→permission assignments.
- **Calculation Logic:** N/A (authorization gate).
- **Conditions:** Every procurement entry point.
- **Exceptions:** None — no permission means no access.
- **Dependencies:** Platform RBAC; PR-BR-018/019/020.
- **Outputs:** Access granted/denied.
- **Business Example:** A cashier with no procurement permissions opens the app.
- **Final Decision:** Workspace hidden.
- **Legacy Evidence:** Legacy enforced by **role**; superseded by permission model.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-018 — Purchase Manager Responsibilities

- **Purpose:** Define what the Purchase Manager may do inside a Refresh.
- **Business Description:** Holds the discrete workspace-decision permissions (Workspace View, Final Qty
  Edit, Skip, Supplier Assign/Change, Pending Finalize, Export Generate/Approve, Reports). **Never** holds
  cycle/refresh/rules/sync permissions.
- **Inputs:** User permissions; Current Refresh.
- **Calculation Logic:** N/A.
- **Conditions:** Within an `ACTIVE` cycle's `CURRENT` refresh.
- **Exceptions:** Export Approval may be separated to a senior approver (AC-04).
- **Dependencies:** PR-BR-017; discrete permissions (AC-02); PR-BR-019/020.
- **Outputs:** Permitted workspace actions.
- **Business Example:** PM edits Final Quantity and assigns a supplier; cannot generate a Refresh.
- **Final Decision:** Decision actions allowed; admin actions denied.
- **Legacy Evidence:** Legacy broad `PURCHASE` perms; replaced by discrete permissions (AC-02).
- **Status:** Ratified · **Version:** 1.0

## PR-BR-019 — Business Cycle Administration

- **Purpose:** Restrict cycle create/close to administrators.
- **Business Description:** Governed by `procurement.cycle.create` / `.close` on platform roles. **No
  dedicated Procurement Administrator role** (AC-01). Not a Purchase Manager responsibility.
- **Inputs:** User permissions.
- **Calculation Logic:** N/A.
- **Conditions:** Cycle create/close.
- **Exceptions:** None.
- **Dependencies:** PR-BR-022; Ratified Decision 1.
- **Outputs:** Permitted/denied cycle administration.
- **Business Example:** Admin opens a cycle; PM cannot.
- **Final Decision:** Allowed only with the permission.
- **Legacy Evidence:** `nx_sp_CreateOrderCycle`/`nx_sp_CloseOrderCycle`; legacy gated by `ADMIN` role.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-020 — Refresh Administration

- **Purpose:** Restrict refresh generation to administrators.
- **Business Description:** Governed by `procurement.refresh.create` / `.close`. Purchase Managers cannot
  generate Refreshes.
- **Inputs:** User permissions.
- **Calculation Logic:** N/A.
- **Conditions:** Refresh create/close.
- **Exceptions:** None.
- **Dependencies:** PR-BR-021; PR-BR-019.
- **Outputs:** Permitted/denied refresh administration.
- **Business Example:** Admin generates Refresh 2; PM works it but cannot create it.
- **Final Decision:** Allowed only with the permission.
- **Legacy Evidence:** `nx_sp_RefreshOrderCycle`; legacy `cycle:refresh` gated by `ADMIN`.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-021 — Automatic Synchronization Before Refresh

- **Purpose:** Guarantee every Refresh uses the latest synced data.
- **Business Description:** A Refresh request auto-triggers Store synchronization, waits for success,
  validates, then generates the Refresh and builds the workspace. Never stale data. Sync is **invoked,
  not exposed**.
- **Inputs:** Refresh request; Sync service status.
- **Calculation Logic:** Orchestration: trigger sync → await success → validate → generate → build workspace.
- **Conditions:** Every Refresh (incl. Refresh 1 via PR-BR-022).
- **Exceptions:** Sync failure/timeout aborts the Refresh.
- **Dependencies:** Sync service; PR-BR-024/025/022.
- **Outputs:** A Refresh built on validated, current data.
- **Business Example:** Admin requests a refresh at 18:00 → platform syncs, then generates.
- **Final Decision:** Refresh proceeds only after successful sync.
- **Legacy Evidence:** Approved (non-legacy). Legacy refresh had no sync gate.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-022 — Business Cycle Creation Workflow

- **Purpose:** Sync-gate cycle creation and seed Refresh 1.
- **Business Description:** sync → create cycle → **auto-generate Refresh 1** → build workspace.
  Subsequent refreshes are independent (each sync-gated, PR-BR-021).
- **Inputs:** Cycle creation request; Sync status.
- **Calculation Logic:** Orchestration as above.
- **Conditions:** On creation; only when no `ACTIVE` cycle exists (Ratified Decision 1).
- **Exceptions:** Sync failure aborts; blocked if an `ACTIVE` cycle exists.
- **Dependencies:** PR-BR-019/021; Ratified Decision 1.
- **Outputs:** New `ACTIVE` cycle + `CURRENT` Refresh 1 + workspace.
- **Business Example:** Admin creates a cycle for "Main" → sync → cycle → Refresh 1.
- **Final Decision:** Cycle + first refresh created together.
- **Legacy Evidence:** Approved (non-legacy). Legacy created cycle with 0 refreshes; first refresh manual.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-023 — Store Completion Notification

- **Purpose:** Signal store operational data entry is complete.
- **Business Description:** Store staff submit **Last GRN Number** + **Last Sale Bill Number**, marking
  completion and triggering automatic sync (PR-BR-024).
- **Inputs:** Last GRN Number; Last Sale Bill Number; store identity.
- **Calculation Logic:** N/A (notification/marker).
- **Conditions:** When store staff finish purchase entry + GRN.
- **Exceptions:** Resubmission updates the markers.
- **Dependencies:** PR-BR-024.
- **Outputs:** A completion marker that initiates sync.
- **Business Example:** Store submits Last GRN 4567, Last Bill 88231.
- **Final Decision:** Sync begins.
- **Legacy Evidence:** VB `OrderHeaderDetails.LastGRN` is the legacy analogue.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-024 — Automatic Store Synchronization

- **Purpose:** Remove manual sync from store users.
- **Business Description:** After a Store Completion Notification the platform auto-starts Store Agent sync.
  Store users never run sync manually.
- **Inputs:** Store Completion Notification (PR-BR-023).
- **Calculation Logic:** N/A (triggered process).
- **Conditions:** Every completion submission.
- **Exceptions:** Retries/failures handled by Sync service.
- **Dependencies:** PR-BR-023; Sync service; PR-BR-025.
- **Outputs:** Synchronized central data.
- **Business Example:** Completion at 17:55 → sync auto-starts.
- **Final Decision:** No manual store action needed.
- **Legacy Evidence:** Approved (non-legacy).
- **Status:** Ratified · **Version:** 1.0

## PR-BR-025 — Synchronization Visibility

- **Purpose:** Keep Procurement independent of Sync administration.
- **Business Description:** Sync is infrastructure. Store Users and Purchase Managers have **no Sync
  panel**; only authorized admins access monitoring/manual controls.
- **Inputs:** User permissions.
- **Calculation Logic:** N/A.
- **Conditions:** All procurement UIs.
- **Exceptions:** None.
- **Dependencies:** Platform sync permission; PR-BR-021/024.
- **Outputs:** Sync controls hidden from procurement users.
- **Business Example:** A PM's UI shows no sync panel.
- **Final Decision:** Sync hidden from procurement.
- **Legacy Evidence:** Confirmed by absence of sync permissions in legacy procurement `permissions.py`.
- **Status:** Ratified · **Version:** 1.0

### Explainability addendum — Governance & Sync rules

| Rule | Reason Code | Displayed Explanation | Decision Explorer Output | Future Dependencies |
|------|-------------|-----------------------|--------------------------|---------------------|
| PR-BR-017 | `ACCESS_GRANTED` / `ACCESS_DENIED_NO_PERMISSION` | "You don't have access to Procurement." | Which permission was missing. | All workspace actions. |
| PR-BR-018 | `ACTION_ALLOWED` / `ACTION_DENIED_NOT_PM_SCOPE` | "This action needs the X permission." | Permission checked vs held. | Workspace decision rules. |
| PR-BR-019 | `CYCLE_ADMIN_OK` / `CYCLE_ADMIN_DENIED` | "Only administrators can create/close cycles." | `procurement.cycle.*` check. | PR-BR-022. |
| PR-BR-020 | `REFRESH_ADMIN_OK` / `REFRESH_ADMIN_DENIED` | "Only administrators can generate refreshes." | `procurement.refresh.*` check. | PR-BR-021. |
| PR-BR-021 | `SYNC_OK_REFRESH` / `SYNC_FAILED_ABORT` | "Synced successfully; generating refresh." / "Sync failed; refresh aborted." | Sync status, timestamp, validation. | Engine run. |
| PR-BR-022 | `CYCLE_CREATED_WITH_REFRESH1` / `CYCLE_BLOCKED_ACTIVE_EXISTS` | "Cycle created and Refresh 1 generated." | Sync result, new cycle/refresh IDs. | Engine run. |
| PR-BR-023 | `STORE_COMPLETION_RECEIVED` | "Completion received (Last GRN / Last Bill)." | Submitted markers. | PR-BR-024. |
| PR-BR-024 | `AUTO_SYNC_STARTED` | "Synchronization started automatically." | Trigger source, sync job ID. | PR-BR-021/022. |
| PR-BR-025 | `SYNC_HIDDEN_FOR_ROLE` | (no sync panel shown) | Why sync UI is hidden. | — |

---

# Domain: Customer Demand (Topic 04)

> **Legacy evidence base:** OrderNMC `customer_demands` (capture-only table: customer_name, mobile,
> remarks, required_qty, product, free-text status, created_by, manager_id), `procurement_rows`
> (`new_customer_demand`, `wanted_type`, `status`), `CustomerProductMatch` (customer→catalogue product
> map, 31,620 rows). VB.NET "Wanted" is an order classification, not a customer demand. Customer Demand
> as a business entity is **essentially greenfield**; the approved architecture is FDD §10.5–10.13.
>
> **Demand example (used below):** Customer "R. Khan" (mobile 98xxxx), product PARA-500, qty 20, type
> "Doctor Request", priority "High".

## PR-BR-026 — Customer Demand Entity & Mandatory Fields

- **Purpose:** Capture a real customer's product requirement as a first-class entity.
- **Business Description:** A demand is an independent business entity (not just an engine input) carrying
  the customer, contact, product, quantity, origin and raiser.
- **Inputs:** Salesman/raiser; Customer Name; Mobile; Remarks; Product; Quantity; Demand Type; Priority.
- **Calculation Logic:** N/A (capture). Mandatory: Salesman (raiser), Customer Name, Mobile, Remarks,
  Product, Quantity (FDD §10.3); a demand cannot be submitted without them.
- **Conditions:** At demand capture.
- **Exceptions:** Missing mandatory field → cannot submit.
- **Dependencies:** PR-BR-027 (status), 028 (priority), 029 (type), 031 (duplicate check), 035 (product match).
- **Outputs:** A persisted demand record.
- **Business Example:** R. Khan requests PARA-500 ×20.
- **Worked Calculation:** N/A.
- **Intermediate Values:** N/A.
- **Final Decision:** Demand created in `Submitted` status.
- **Reason Code:** `DEMAND_CREATED`.
- **Displayed Explanation:** "Demand for PARA-500 ×20 raised for R. Khan."
- **Decision Explorer Output:** Full captured fields + raiser + timestamp.
- **Future Decision Dependencies:** Inclusion into a Refresh (engine), traceability (PR-BR-033).
- **Legacy Evidence:** `customer_demands` columns (customer_name, mobile, remarks, required_qty,
  product_id/label, created_by). **Extended:** type & priority added.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-027 — Demand Status Model & Lifecycle

- **Purpose:** Govern the demand's life with a formal, auditable status model.
- **Business Description:** Formal states: Draft → Submitted → Under Review → Approved → Waiting
  Procurement → Included In Refresh → Ordered → Partially Received → Ready For Customer → Delivered →
  Closed; plus Rejected and Cancelled. Terminal: Rejected, Closed, Cancelled.
- **Inputs:** Current status; transition event; actor permission.
- **Calculation Logic:** Allowed transitions per the lifecycle; each transition is audited with a reason
  (PR-BR-032). Replaces legacy free-text `status`.
- **Conditions:** Every state change.
- **Exceptions:** No transitions out of a terminal state.
- **Dependencies:** PR-BR-032 (reasons), 033 (trace), 018/019 (who may act).
- **Outputs:** New status + audit entry.
- **Business Example:** R. Khan's demand: Submitted → Under Review → Approved.
- **Worked Calculation:** N/A.
- **Intermediate Values:** status history list.
- **Final Decision:** `Approved` (awaiting procurement).
- **Reason Code:** `DEMAND_STATUS_CHANGED` (+ specific e.g. `DEMAND_APPROVED`).
- **Displayed Explanation:** "Approved — moved to Waiting Procurement."
- **Decision Explorer Output:** Ordered status timeline with reasons/actors.
- **Future Decision Dependencies:** Inclusion, ordering, receipt, delivery.
- **Legacy Evidence:** `customer_demands.status` (informal varchar). **Corrected** to formal model.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-028 — Demand Priority

- **Purpose:** Let urgent demands surface first without bypassing governance.
- **Business Description:** Configurable priority ladder (e.g. Normal/High/Urgent/Emergency). Priority
  **orders the workspace** Customer Demand section but **never bypasses approval**.
- **Inputs:** Priority value (configurable set, PR-BR-016-style configuration).
- **Calculation Logic:** Workspace sort key = (priority rank, …). Priority does not alter the approval path.
- **Conditions:** At capture and during workspace ordering.
- **Exceptions:** Even `Emergency` passes Under Review → Approved.
- **Dependencies:** PR-BR-027 (approval still required), Workspace ordering (Topic 02).
- **Outputs:** Priority on the demand; workspace ordering.
- **Business Example:** R. Khan's demand = High.
- **Worked Calculation:** sorts above Normal demands in the section.
- **Intermediate Values:** priority_rank.
- **Final Decision:** Shown higher in the queue; still requires approval.
- **Reason Code:** `DEMAND_PRIORITY_SET`.
- **Displayed Explanation:** "High priority — listed before normal demands."
- **Decision Explorer Output:** priority and its effect on ordering.
- **Future Decision Dependencies:** Workspace/section ordering; supplier urgency.
- **Legacy Evidence:** Approved decision (non-legacy) — absent in `customer_demands`.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-029 — Demand Type / Origin

- **Purpose:** Record where the demand originated.
- **Business Description:** Configurable, extensible origin type: Customer Request, Doctor Request,
  Hospital Requirement, Special Order, Manual Purchase (more may be added).
- **Inputs:** Demand Type value.
- **Calculation Logic:** N/A (classification). Must remain **distinct from** order `wanted_type`.
- **Conditions:** At capture.
- **Exceptions:** Unknown type rejected unless configured.
- **Dependencies:** Configuration; PR-BR-026.
- **Outputs:** Demand Type on the record.
- **Business Example:** "Doctor Request".
- **Worked Calculation:** N/A.
- **Intermediate Values:** N/A.
- **Final Decision:** Type = Doctor Request.
- **Reason Code:** `DEMAND_TYPE_SET`.
- **Displayed Explanation:** "Origin: Doctor Request."
- **Decision Explorer Output:** type; used in history/segmentation.
- **Future Decision Dependencies:** History (PR-BR-030); reporting.
- **Legacy Evidence:** Absent (`wanted_type` is a different, order-side concept). Approved (non-legacy).
- **Status:** Ratified · **Version:** 1.0

## PR-BR-030 — Customer History

- **Purpose:** Give the Purchase Manager instant context at review time.
- **Business Description:** For this customer + product, show: prior request? previously fulfilled?
  previously cancelled? average fulfilment time; repeat-request frequency.
- **Inputs:** Past demands (PR-BR-026/027 records); `CustomerProductMatch` (PR-BR-035) for product
  resolution.
- **Calculation Logic:** Aggregate the customer's prior demands for the (matched) product: counts of
  fulfilled/cancelled, `AVG(delivered_at − created_at)`, repeat count.
- **Conditions:** On review/approval of a demand.
- **Exceptions:** No history → "first request".
- **Dependencies:** PR-BR-027 (status timeline), 035 (product match).
- **Outputs:** Customer history summary.
- **Business Example:** R. Khan previously requested PARA-500 twice, both fulfilled, avg 3 days.
- **Worked Calculation:** fulfilled=2, cancelled=0, avg=3d, repeats=2.
- **Intermediate Values:** as above.
- **Final Decision:** "Reliable repeat request — approve."
- **Reason Code:** `CUSTOMER_HISTORY_SHOWN`.
- **Displayed Explanation:** "R. Khan: 2 prior PARA-500 requests, both fulfilled, avg 3 days."
- **Decision Explorer Output:** the history metrics behind a decision.
- **Future Decision Dependencies:** Approval/priority judgement.
- **Legacy Evidence:** `CustomerProductMatch` (raw map only) — aggregation is new.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-031 — Duplicate Active Demand Validation

- **Purpose:** Prevent silent duplicate demands.
- **Business Description:** If an **active** demand already exists for the same **Customer × Product**, warn
  the user; never silently create a duplicate. Active = any non-terminal status.
- **Inputs:** New demand (customer, product); existing demands.
- **Calculation Logic:** Exists active demand where `customer = X AND product = Y AND status NOT IN
  (Rejected, Closed, Cancelled)` → **warn**.
- **Conditions:** At capture/submit.
- **Exceptions:** User may proceed referencing/augmenting the existing demand.
- **Dependencies:** PR-BR-027 (status), 035 (product match for X/Y identity).
- **Outputs:** Warning + link to the existing active demand.
- **Business Example:** R. Khan already has an active PARA-500 demand.
- **Worked Calculation:** match found (status `Approved`).
- **Intermediate Values:** duplicate=TRUE.
- **Final Decision:** Warn; offer to view the existing demand.
- **Reason Code:** `DEMAND_DUPLICATE_WARNING`.
- **Displayed Explanation:** "An active demand for R. Khan / PARA-500 already exists."
- **Decision Explorer Output:** the matched existing demand id/status.
- **Future Decision Dependencies:** Decision-Explorer reason `Duplicate` (PR-BR-034).
- **Legacy Evidence:** Absent. Approved (non-legacy).
- **Status:** Ratified · **Version:** 1.0

## PR-BR-032 — Demand Explainability

- **Purpose:** Make every demand decision auditable with a reason.
- **Business Description:** Every demand records **why** it was approved, rejected, delayed or cancelled;
  the reason becomes part of audit history.
- **Inputs:** Decision event; reason text/code; actor.
- **Calculation Logic:** N/A (recording). Reason persisted with each status transition (PR-BR-027).
- **Conditions:** On approve/reject/delay/cancel.
- **Exceptions:** None — reason mandatory for these transitions.
- **Dependencies:** PR-BR-027; audit (FDD §14).
- **Outputs:** Reason code + text on the audit entry.
- **Business Example:** Rejected because product discontinued.
- **Worked Calculation:** N/A.
- **Intermediate Values:** N/A.
- **Final Decision:** Status `Rejected`, reason stored.
- **Reason Code:** `DEMAND_APPROVED` / `DEMAND_REJECTED` / `DEMAND_DELAYED` / `DEMAND_CANCELLED`.
- **Displayed Explanation:** "Rejected: product discontinued."
- **Decision Explorer Output:** the reason for each demand decision.
- **Future Decision Dependencies:** PR-BR-034 (why not converted).
- **Legacy Evidence:** Absent. Approved (non-legacy).
- **Status:** Ratified · **Version:** 1.0

## PR-BR-033 — Demand → Procurement Traceability

- **Purpose:** Make every approved demand traceable end-to-end, both directions.
- **Business Description:** Persist the linking chain: Demand → Business Cycle → Refresh → Workspace Item →
  Supplier Assignment → Supplier Order → GRN → Delivery; navigable forward and backward.
- **Inputs:** Linking identifiers at each hop.
- **Calculation Logic:** N/A (linkage). Each stage stores the upstream id(s); reverse lookup supported.
- **Conditions:** As the demand progresses through procurement.
- **Exceptions:** Unconverted demands link only as far as they reached (+ reason, PR-BR-034).
- **Dependencies:** Refresh (Topic 01/03), Workspace (02), Assignment/Export (06), GRN (07).
- **Outputs:** A navigable trace per demand.
- **Business Example:** R. Khan's demand → Cycle 7 → Refresh 3 → row #812 → supplier MEDline → order
  PO-559 → GRN 4570 → delivered.
- **Worked Calculation:** N/A.
- **Intermediate Values:** chain of ids.
- **Final Decision:** Full forward/back navigation available.
- **Reason Code:** `DEMAND_TRACE_LINKED`.
- **Displayed Explanation:** "Trace: Demand → … → Delivery."
- **Decision Explorer Output:** the full chain from either end.
- **Future Decision Dependencies:** all downstream topics.
- **Legacy Evidence:** Legacy only had `procurement_rows.new_customer_demand` flag — **insufficient**;
  replaced by a proper link chain.
- **Status:** Ratified · **Version:** 1.0

## PR-BR-034 — Demand Decision Explorer (not converted)

- **Purpose:** Explain why an approved demand did **not** become a procurement item.
- **Business Description:** When a demand is not converted in a Refresh, store a controlled reason so its
  absence is explainable.
- **Inputs:** Demand state; engine outcome.
- **Calculation Logic:** N/A (recording). Reason ∈ { `Rejected`, `Duplicate`, `Already Ordered`,
  `Pending Receipt`, `Skip Until Next Demand`, `Closed`, `Cancelled`, `Stock Already Sufficient` }.
- **Conditions:** Per Refresh, for each demand not converted.
- **Exceptions:** Converted demands carry the engine reason codes (PR-BR-015) instead.
- **Dependencies:** PR-BR-015 (engine reasons), 031 (duplicate), Pending (Topic 05), Skip (FDD §9).
- **Outputs:** Non-conversion reason on the demand for the Refresh.
- **Business Example:** Demand not converted because stock already sufficient.
- **Worked Calculation:** N/A.
- **Intermediate Values:** reason=`Stock Already Sufficient`.
- **Final Decision:** Recorded; surfaced in the Explorer.
- **Reason Code:** `DEMAND_NOT_CONVERTED` (+ specific reason above).
- **Displayed Explanation:** "Not procured: stock already sufficient."
- **Decision Explorer Output:** answers "Why did this demand not become a procurement item?".
- **Future Decision Dependencies:** ties to Pending (05) and Skip Until Next Demand (FDD §9.3).
- **Legacy Evidence:** Absent. Approved (non-legacy).
- **Status:** Ratified · **Version:** 1.0

## PR-BR-035 — Customer Product Match

- **Purpose:** Resolve a customer's own product wording to the catalogue product.
- **Business Description:** Map a customer's product code/name to the platform `ProductCode`, enabling
  accurate capture, duplicate detection and history for that customer.
- **Inputs:** `CustomerCode`, `CustomerProductCode`/`Name`; catalogue `ProductCode`.
- **Calculation Logic:** Lookup `CustomerProductMatch` to resolve the catalogue product for a customer's
  requested item.
- **Conditions:** At demand capture and history aggregation.
- **Exceptions:** No match → capture as free product_label, flag for matching.
- **Dependencies:** PR-BR-026/030/031.
- **Outputs:** Resolved `ProductCode` for the demand.
- **Business Example:** Customer's "Paracetamol 500" → PARA-500.
- **Worked Calculation:** match on CustomerProductName → ProductCode.
- **Intermediate Values:** resolved ProductCode.
- **Final Decision:** Demand bound to PARA-500.
- **Reason Code:** `CUSTOMER_PRODUCT_MATCHED` / `CUSTOMER_PRODUCT_UNMATCHED`.
- **Displayed Explanation:** "Matched 'Paracetamol 500' → PARA-500."
- **Decision Explorer Output:** how the customer's wording resolved to the catalogue.
- **Future Decision Dependencies:** History (030), duplicate check (031).
- **Legacy Evidence:** `CustomerProductMatch` table (31,620 rows). **Preserved.**
- **Status:** Analysed · **Version:** 1.0
