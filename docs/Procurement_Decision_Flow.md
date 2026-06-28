---
module: Procurement
version: 1.0
status: Active
owner: Solution Architecture
updated: 2026-06-27
---

# NEXORA Platform — Procurement Decision Flow

> **Purpose:** Define the **complete, ordered execution sequence** of the Procurement Decision Engine —
> the runtime pipeline that turns a Refresh request into explainable `order_virtual_items`.
>
> This document is **independent of** the Business Rule Catalogue (`Procurement_Business_Rules.md`):
> the catalogue defines *what each rule means* (atomic, testable); this document defines *the order in
> which they run* and *how data flows between them*. Rule IDs (`PR-BR-NNN`) are cross-references.
> No code, no SQL — this is the authoritative execution specification.

## Scope

Covers the engine from **Refresh request** to **persisted, explainable decisions**. Upstream
synchronization (PR-BR-021/022/024) and downstream Workspace/Assignment/Export are referenced at the
boundaries only. Reflects the approved corrections of 2026-06-27 (Rolling Days, protection floors,
Effective Available, configurable parameters, explainability).

---

## 1. High-level pipeline

```
[Refresh request (admin)]
        │  PR-BR-020 permission
        ▼
[STAGE 0  Sync gate]            PR-BR-021/022  → trigger sync, await success, validate
        ▼
[STAGE 1  Load parameters]      PR-BR-016      → Rolling Days (cycle), Min/Max Days (refresh), cut-offs
        ▼
[STAGE 2  Compute metrics]      PR-BR-001/002/012  per product (eligible window sales)
        ▼
[STAGE 3  Effective Available]  PR-BR-014      per product (stock + incoming − reserved)
        ▼
[STAGE 4  Days Cover + Class]   PR-BR-003/010/011
        ▼
[STAGE 5  Candidate filter]     PR-BR-004      include / exclude (+ exclusion reason codes)
        ▼
[STAGE 6  Coverage sizing]      PR-BR-005/006  Target, CoverageRequired
        ▼
[STAGE 7  Protection floors]    PR-BR-007/008  raise to MAX(coverage, MaxDaySale, MaxBill)
        ▼
[STAGE 8  Finalize quantity]    PR-BR-009      CEILING; drop ≤0; determining reason
        ▼
[STAGE 9  Reason codes]         PR-BR-015      inclusion/exclusion + quantity reason + text
        ▼
[STAGE 10 Persist snapshot]     write order_virtual_items (incl. excluded, for explainability)
        ▼
[Workspace ready]               Topic 02
```

---

## 2. Stage-by-stage specification

### STAGE 0 — Sync gate (pre-engine)
- **Trigger:** Refresh request by a user holding `procurement.refresh.create` (PR-BR-020).
- **Action:** Automatically trigger Store synchronization; **wait** for successful completion; **validate**
  sync status (PR-BR-021). For a new cycle, this is part of creation and seeds Refresh 1 (PR-BR-022).
- **Failure:** Sync failure/timeout → **abort**, no Refresh generated. Reason `SYNC_FAILED_ABORT`.
- **Output:** Confirmation that central data is current.

### STAGE 1 — Load parameters (PR-BR-016)
- Read **Rolling Days** from the **Business Cycle** (default 90; never hard-coded).
- Read **Min Days** and **Max Days** from the **Refresh** (`MaxDays ≥ MinDays > 0`).
- Read classification cut-offs (Movement Fast/Medium, Stock Low/Safe) from platform/store config.
- Record the effective parameter set on the Refresh for explainability (`PARAMS_APPLIED`).

### STAGE 2 — Compute metrics (PR-BR-001, 002, 012)
- Build the **eligible sales set**: `TransactionValidity=0 AND DontConsiderInOrder=0 AND
  TransactionDate ≥ today − RollingDays`, active products only (PR-BR-001, 013).
- Compute per product: `AvgDailySales = WindowQty / RollingDays` (PR-BR-002); `MaxDaySaleQty`,
  `MaxBillQty`, `WindowSalesQty`, `BillingFrequency` (PR-BR-012).

### STAGE 3 — Effective Available (PR-BR-014)
- `EffectiveAvailable = CurrentStock + PendingReceivable + ConfirmedInTransit − ReservedQuantity`.
- This value (not raw stock) feeds cover and coverage sizing. (Component sourcing finalised in Topic 05.)

### STAGE 4 — Days Cover, Movement Class, Stock Status (PR-BR-003, 010, 011)
- `DaysCover = EffectiveAvailable / AvgDailySales` (0 if avg ≤ 0).
- `MovementClass` from `AvgDailySales` vs cut-offs; `StockStatus` from `DaysCover`/availability vs cut-offs.

### STAGE 5 — Candidate filter (PR-BR-004)
- **Include** iff `AvgDailySales > 0 AND DaysCover < MinDays`.
- **Exclude** otherwise, recording the exclusion reason: `EXCLUDED_NOT_SELLING`,
  `EXCLUDED_ADEQUATE_COVER`, `EXCLUDED_FLAGGED`, `EXCLUDED_INACTIVE`.
- Excluded products are **retained** for explainability (Stage 10), not discarded.

### STAGE 6 — Coverage sizing (PR-BR-005, 006)
- `TargetStockQty = AvgDailySales × MaxDays`.
- `CoverageRequired = TargetStockQty − EffectiveAvailable`.

### STAGE 7 — Protection floors (PR-BR-007, 008)
- Apply **minimum protection quantities** (floors, not caps):
  `Required = MAX(CoverageRequired, MaxDaySaleQty, MaxBillQty)`.
- Track which term is binding (for the determining reason).

### STAGE 8 — Finalize quantity (PR-BR-009)
- `FinalRequiredQty = CEILING(Required)`.
- If `FinalRequiredQty ≤ 0` → exclude with `EXCLUDED_ZERO_REQUIRED`.
- **Determining reason** = the argument equal to the MAX: `COVERAGE` | `SPIKE_PROTECTION` |
  `MAX_BILL_TRIGGER`.

### STAGE 9 — Reason codes & text (PR-BR-015)
- Persist per product: inclusion/exclusion **Reason Code**, final-quantity **determining Reason Code**,
  and human-readable **Reason Text**.

### STAGE 10 — Persist snapshot
- Write `order_virtual_items` for the Refresh: metrics, EffectiveAvailable components, target, coverage,
  floors, final quantity, movement class, stock status, **and the reason codes/text** — including
  **excluded** products (flagged) so the Decision Explorer can answer "why excluded?".
- Refresh becomes `CURRENT`; the prior `CURRENT` becomes `SUPERSEDED` (immutable).

---

## 3. Decision Explorer contract

For any product in a Refresh, the future **Procurement Decision Explorer** must answer, from the persisted
snapshot (PR-BR-015):

| Question | Answered from |
|----------|---------------|
| Why is this product **included**? | inclusion Reason Code + Stage 5 values (DaysCover < MinDays). |
| Why is this product **excluded**? | exclusion Reason Code (Stage 5 or 8) + the failing condition. |
| Which **rules were evaluated**? | the ordered stage trace (Stages 1–9) with each rule's output. |
| Which rule **determined the final quantity**? | determining Reason Code (`COVERAGE` / `SPIKE_PROTECTION` / `MAX_BILL_TRIGGER`). |
| What **parameters** were used? | the recorded effective parameter set (Stage 1, `PARAMS_APPLIED`). |
| Why did a **Customer Demand** not become a procurement item? | demand non-conversion reason (PR-BR-034): `Rejected`/`Duplicate`/`Already Ordered`/`Pending Receipt`/`Skip Until Next Demand`/`Closed`/`Cancelled`/`Stock Already Sufficient`. |

---

## 4. Worked trace (running example PARA-500)

Parameters: Rolling 90, Min 10, Max 20. Window: 900 units, peak day 40, peak bill 60, 120 bills.
Stock 30, Pending Receivable 50, In Transit 0, Reserved 10.

| Stage | Computation | Result |
|-------|-------------|--------|
| 2 | AvgDailySales = 900/90 | **10/day**; MaxDaySale 40; MaxBill 60 |
| 3 | EffectiveAvailable = 30+50+0−10 | **70** |
| 4 | DaysCover = 70/10 | **7**; MovementClass MEDIUM; StockStatus SAFE |
| 5 | 10>0 AND 7<10 | **Included** (`INCLUDED_BELOW_MIN_DAYS`) |
| 6 | Target = 10×20 = 200; Coverage = 200−70 | **130** |
| 7 | MAX(130, 40, 60) | **130** (coverage binding) |
| 8 | CEILING(130) | **FinalRequiredQty = 130**; reason `COVERAGE` |
| 9 | reason text | "Included; 130 units; driven by coverage to the 200 target; floors 40/60 not binding." |

---

## 5. Boundaries & forward dependencies

- **Customer Demand** (Topic 04) is a **first-class entity** (FDD §10.5–10.13) that, once **Approved**,
  adds demand **on top of** the replenishment baseline (additive), then re-nets against Effective
  Available. Approved demands link into the Refresh (status `Included In Refresh`, PR-BR-027/033); demands
  not converted store a non-conversion reason (PR-BR-034) for the Decision Explorer.
- **Pending** (Topic 05) finalises the components of Effective Available (Pending Receivable, In Transit,
  Reserved) and carry-forward.
- **Supplier Assignment / Export** (Topic 06) consume `final_required_qty`.
- **GRN Reconciliation** (Topic 07) updates pending and thus future Effective Available.

*This execution sequence is authoritative for the engine's future stored procedures, APIs, UI and tests.*
