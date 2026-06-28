---
module: Procurement
version: 0.1
status: Draft
owner: Solution Architecture
updated: 2026-06-27
---

# Procurement V1 — Business Analysis

## Topic 03: Decision Engine

> **Method:** Search-first, matching regions only. Code is evidence; the FDD and the **Business Rule
> Catalogue** (`Procurement_Business_Rules.md`) are the outputs. No code generated, no redesign.
>
> **Evidence read (Topic 03 only):**
> - OrderNMC stored procedures: `nx_sp_BuildVirtualProductList` (decision), `nx_sp_GetProductProcurementMetrics` (metrics).
> - Legacy VB.NET `Form1.vb`: matched regions only — `MinDays=15 / MaxDays=20` defaults (ln 49–50),
>   metric columns (`slsqty`="90 Sls", `maxsaleqty`, `wantedtype`="Wanted", `totalstock`, `lastsaledate`),
>   `result.MinDays/MaxDays` load (ln 554–555).

---

### 1. Business Summary

The Decision Engine turns synced sales + stock into a **suggested order quantity** per product for a
Refresh. It runs in two stored procedures: a **metrics** pass that computes per-product sales behaviour
(average daily sales, max day/bill, days of cover, movement class, stock status) over a rolling window,
and a **decision** pass that selects under-covered products and sizes the order up to a Max-Days target,
with **spike-protection floors**. Output rows are the `order_virtual_items` that populate the Workspace.

The engine is **purely stock-replenishment**: it considers only products that are **selling** and
**below the Min-Days cover**. It does **not** yet incorporate Customer Demand, Pending, or supplier
offers (those are Topics 04–06 and gaps below).

---

### 2. Current Implementation

**Pass 1 — Metrics (`nx_sp_GetProductProcurementMetrics`, `@RollingDays = 30`):**

- Source: `ProductSaleInformation`, filtered `TransactionValidity = 0` (valid sales only),
  `DontConsiderInOrder = 0` (not excluded), `TransactionDate >= today − RollingDays`.
- `AvgDailySales = SUM(Quantity) / RollingDays`.
- `MaxDaySaleQty = MAX(per-day total)`, `MaxBillQty = MAX(per-bill total)`,
  `MonthlySalesQty = SUM(Quantity)` (window total), `BillingFrequency = COUNT(DISTINCT BillNumber)`.
- Joined to `Products` (`IsActive = 1`): `CurrentStock = TotalStock`;
  `DaysCover = TotalStock / AvgDailySales` (0 if avg≤0).
- `StockStatus`: `OUT` (stock≤0) · `LOW` (cover<3) · `SAFE` (cover≤15) · `OVERSTOCK` (else).
- `MovementClass`: `FAST` (avg≥50) · `MEDIUM` (avg≥10) · `SLOW` (avg>0) · `NONMOVING` (else).

**Pass 2 — Decision (`nx_sp_BuildVirtualProductList`, `@MinDays`, `@MaxDays` from the Refresh):**

1. Delete prior rows for this `refresh_id` (idempotent rebuild).
2. Candidate filter: `AvgDailySales > 0 AND DaysCover < MinDays`.
3. `TargetStockQty = AvgDailySales × MaxDays`.
4. `RawRequiredQty = TargetStockQty − CurrentStock`.
5. **Spike protection (floors):** if `Raw < MaxDaySaleQty` → `Raw = MaxDaySaleQty` (`SPIKE_PROTECTION`);
   then if `Raw < MaxBillQty` → `Raw = MaxBillQty` (`MAX_BILL_TRIGGER`). Net: `Raw = MAX(Raw,
   MaxDaySaleQty, MaxBillQty)`.
6. `FinalRequiredQty = CEILING(Raw)`; drop rows where `Final ≤ 0`.
7. Insert into `order_virtual_items` (stores stock, metrics, target, raw/final qty, min/max days,
   movement class, stock status, trigger reason).

**VB.NET (original):** `MinDays = 15`, `MaxDays = 20` defaults; the working grid showed `slsqty`
("**90 Sls**" — a **90-day** sales figure), `maxsaleqty`, and `wantedtype` (a "Wanted"/procurement
classification). The desktop computed off a **90-day** window and a "WantedType" category — the analogue
of the Python `MovementClass`.

---

### 3. Business Rules (extracted → catalogued)

These are catalogued in full in `Procurement_Business_Rules.md`:

| Catalogue ID | Rule |
|--------------|------|
| PR-BR-001 | Rolling Sales Window & Eligibility (validity, `DontConsiderInOrder`, rolling days) |
| PR-BR-002 | Average Daily Sales (`= windowQty / RollingDays`) |
| PR-BR-003 | Days Cover (`= CurrentStock / AvgDailySales`) |
| PR-BR-004 | Min-Days Reorder Trigger (`AvgDailySales>0 AND DaysCover<MinDays`) |
| PR-BR-005 | Max-Days Target Stock (`= AvgDailySales × MaxDays`) |
| PR-BR-006 | Raw Required Quantity (`= Target − CurrentStock`) |
| PR-BR-007 | Max-Day-Sale Spike Floor |
| PR-BR-008 | Max-Bill-Quantity Floor |
| PR-BR-009 | Final Required Quantity (`CEILING`; drop ≤0) |
| PR-BR-010 | Movement Class (FAST/MEDIUM/SLOW/NONMOVING) |
| PR-BR-011 | Stock Status (OUT/LOW/SAFE/OVERSTOCK) |
| PR-BR-012 | Sales Behaviour Metrics (MaxDaySale, MaxBill, MonthlySales, BillingFrequency) |
| PR-BR-013 | Order-Exclusion Flag (`DontConsiderInOrder`, `TransactionValidity`, `IsActive`) |

---

### 4. Missing Rules (in the FDD / spec but absent in the engine)

- **M-01 — Pending Deduction.** The engine sizes `Raw = Target − CurrentStock` only. It does **not**
  subtract outstanding pending (FDD §8.10). **This risks double-ordering** and conflicts with Topic-01
  D2 (pending carries forward and must be netted). **High priority.**
- **M-02 — Customer Demand.** Demand is not added into the engine (FDD §8.8). Only stock-replenishment
  candidates are produced. (Topic 04.)
- **M-03 — Offer Based Purchase.** No above-Max-Days offer buying (FDD §8.9).
- **M-04 — Monthly Once Sold.** No explicit slow-mover/demand-only handling beyond `MovementClass`
  (FDD §8.7). Non-selling items are simply excluded (`AvgDailySales>0` gate).
- **M-05 — Manual Override / Compare Refresh / Section & Priority.** The engine emits no `section` or
  `priority` and computes `ProcurementAction` but **stores it as NULL** (incomplete).

### 4b. Extra Rules (in the engine but not in the FDD)

- **X-01 — Spike-protection floors** (MaxDaySale, MaxBill) — order at least the largest observed
  single-day and single-bill quantity.
- **X-02 — Movement Class** (FAST≥50 / MEDIUM≥10 / SLOW>0 / NONMOVING).
- **X-03 — Stock Status** (OUT / LOW<3 / SAFE≤15 / OVERSTOCK).
- **X-04 — `DontConsiderInOrder` exclusion** flag — products explicitly held out of ordering.

---

### 5. Conflicts

| # | Conflict | Detail | Severity |
|---|----------|--------|----------|
| C-01 | **Rolling window hard-coded to 30 days.** | `nx_sp_BuildVirtualProductList` calls the metrics SP with `@RollingDays = 30`, **ignoring the cycle's `rolling_days` (default 90)** and contradicting the VB "90 Sls" (90-day) basis. The cycle parameter is stored but unused by the engine. | **High** — the "90-day average" is actually a 30-day average; violates D4 (Rolling Days drives the engine). |
| C-02 | **MaxBillQty / MaxDaySaleQty are FLOORS, not CAPS.** | The engine raises the order **up to** the largest day/bill quantity (coverage). The FDD §8.5/§8.6 describe them as **caps** to prevent over-ordering. The legacy (real business) behaviour is the **opposite**. | **High** — FDD wording must be corrected to the real rule (floor/coverage). |
| C-03 | **No Pending Deduction in sizing.** | `Raw = Target − Stock` omits pending (see M-01). | **High** — double-order risk. |
| C-04 | **Magic-number thresholds.** | `StockStatus` (3, 15) and `MovementClass` (50, 10) are hard-coded, store-agnostic constants, separate from Min/Max Days. | Medium — not configurable; should be parameters. |
| C-05 | **`ProcurementAction` computed but discarded** (stored NULL). | Engine prepares an action label but does not persist it. | Low — incomplete output. |
| C-06 | **Engine is replenishment-only.** | No demand/offer/pending integration; only `AvgDailySales>0 AND DaysCover<MinDays`. | Medium — by-design now, but the spec expects an integrated decision. |

---

### 6. Recommended Design (documentation-level, no code)

1. **Drive the rolling window from the cycle's Rolling Days** (resolve C-01): the engine must use the
   cycle `rolling_days` (default 90), not a hard-coded 30. Preserve D4's separation: Rolling Days
   (window) is cycle-level; Min/Max Days (cover) are refresh-level.
2. **Correct the FDD to the real MaxBill/MaxDaySale rule** (resolve C-02): document them as **coverage
   floors / spike protection** ("order at least the largest single-day and single-bill quantity"), not
   caps. *Business reality wins; do not redesign it into a cap.*
3. **Add Pending Deduction to sizing** (resolve C-03/M-01): `Raw = Target − CurrentStock − OutstandingPending`,
   consistent with Topic-01 D2 and FDD §8.10. (Detail finalised in Topic 05.)
4. **Promote thresholds to configurable parameters** (C-04): `StockStatus` and `MovementClass` cut-offs
   per store/rule-set, governed by `procurement.rules.manage`.
5. **Persist `section`, `priority`, and `ProcurementAction`** on `order_virtual_items` so the Workspace
   sections (Topic 02) and the discarded action label are realised (C-05, M-05).
6. **Keep the valuable legacy classifications** (MovementClass, StockStatus, spike floors,
   `DontConsiderInOrder`) as first-class catalogued rules — they are real accumulated business logic.
7. Integrate **Customer Demand** (Topic 04) and **Offer** (later) as **additive** inputs on top of the
   replenishment baseline, then net Pending.

---

### 7. Questions (for business owner sign-off)

1. **Rolling window:** Confirm the engine must use the cycle's **Rolling Days (90)**, not the hard-coded
   **30**. Was 30 intentional, or drift in the rewrite? (VB used 90.)
2. **Max Bill / Max Day Sale:** Confirm these are **coverage floors** (order at least that much), as the
   legacy engine does — and correct the FDD accordingly?
3. **Pending deduction:** Confirm the engine must **net outstanding pending** when sizing (to avoid
   double-ordering)?
4. **Thresholds:** Should `StockStatus` (3/15) and `MovementClass` (50/10) be **configurable** rather
   than hard-coded?
5. **Monthly Once Sold:** Is a distinct slow-mover/demand-only rule wanted, or is `MovementClass`
   (SLOW/NONMOVING) sufficient?

---

*Topic 03 in progress — engine baseline captured and catalogued (PR-BR-001…013). Demand, Offer and
Pending integration continue in Topics 04–05. Next: **Topic 04 — Customer Demand**.*
