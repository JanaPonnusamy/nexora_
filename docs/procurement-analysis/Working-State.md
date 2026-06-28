---
module: Procurement
version: 1.0
status: Active
owner: Solution Architecture
updated: 2026-06-27
---

# Procurement V1 — Business Analysis Working State

> Living tracker for the Procurement V1 business-knowledge extraction. Records topic progress,
> the ratified decision log, and open clarifications. The **FDD**
> (`Procurement_Business_Architecture_Specification.md`) is the target design; **Evidence.md**
> holds source provenance; the per-topic docs hold the analysis.

## Topic progress

| # | Topic | Status | Output |
|---|-------|--------|--------|
| 01 | Business Cycle | ✅ Ratified | `Topic-01-Business-Cycle.md`; FDD §5–6 updated |
| 02 | Procurement Workspace | 📝 Analysed — awaiting sign-off | `Topic-02-Procurement-Workspace.md` |
| 03 | Decision Engine | ✅ Approved & frozen | `Topic-03-Decision-Engine.md`; catalogue PR-BR-001…016 |
| 04 | Customer Demand | 📝 Analysed — awaiting sign-off | `Topic-04-Customer-Demand.md`; FDD §10.5–10.13; catalogue PR-BR-026…035 |
| 05 | Pending | ⬜ Pending | — |
| 06 | Supplier Assignment | ⬜ Pending | — |
| 07 | GRN Reconciliation | ⬜ Pending | — |

## Ratified decision log

| ID | Date | Topic | Decision |
|----|------|-------|----------|
| D1 | 2026-06-27 | 01 | Business Cycle is closed **explicitly** by the Purchase Manager; **never auto-closed**. A second cycle cannot be created while one is `ACTIVE`. |
| D2 | 2026-06-27 | 01 | **Pending does not block closure.** Pending **carries forward** into the next Business Cycle until finalized. |
| D3 | 2026-06-27 | 01 | **Exactly one `CURRENT` Refresh.** Older Refreshes become immutable `SUPERSEDED` history. |
| D4 | 2026-06-27 | 01 | Preserve separation: **Rolling Days (cycle)**, **Min Days (refresh)**, **Max Days (refresh)**. |
| D5 | 2026-06-27 | 01 | **Standardize status values.** Cycle: `ACTIVE`/`CLOSED`. Refresh: `GENERATING`/`CURRENT`/`SUPERSEDED`. Legacy casing/names dropped. |

## Canonical status vocabulary (authoritative)

| Entity | Statuses |
|--------|----------|
| Business Cycle | `ACTIVE` → `CLOSED` |
| Refresh | `GENERATING` → `CURRENT` → `SUPERSEDED` |
| *(Assignment / Export / Demand / Pending — TBD in Topics 04–07)* | — |

## Approved business rules — Roles & Sync Orchestration (PR-BR-017…025, 2026-06-27)

These are **approved** (not extracted from legacy); incorporated into FDD §3.4–3.6, §5.4/5.4a, §6.6, §7.0.

| ID | Rule (summary) |
|----|----------------|
| PR-BR-017 | **Role-Based Procurement Access** — Procurement is restricted; Workspace not visible to normal users. |
| PR-BR-018 | **Purchase Manager Responsibilities** — owns Final Qty, Skip, Supplier Assignment, Manual Overrides, Pending Finalization, Export Approval. Cannot create cycle/refresh, run sync, or configure rules. |
| PR-BR-019 | **Business Cycle Administration** — create/close only by Super Admin / Admin / Procurement Admin permission. Not a Purchase Manager task. |
| PR-BR-020 | **Refresh Administration** — same permission model; Purchase Managers cannot generate Refreshes. |
| PR-BR-021 | **Auto-Sync Before Refresh** — refresh request → trigger sync → wait/validate → generate refresh → build workspace. Never stale data. |
| PR-BR-022 | **Cycle Creation Workflow** — sync → create cycle → auto-generate **Refresh 1** → build workspace. Subsequent refreshes independent. |
| PR-BR-023 | **Store Completion Notification** — store submits Last GRN Number + Last Sale Bill Number to signal data-entry complete. |
| PR-BR-024 | **Automatic Store Synchronization** — submission auto-starts Store Agent sync; store users never run sync manually. |
| PR-BR-025 | **Synchronization Visibility** — no Sync panel for Store Users or Purchase Managers; only admins. Procurement independent of Sync admin. |

**Architecture principle:** Synchronization is a platform service. Procurement *consumes* synced data and
*invokes* (never manages/exposes) Sync during Cycle/Refresh orchestration.

## Canonical access model (authoritative) — permissions, not procurement roles (AC-01…AC-04)

Procurement uses the **existing Nexora Platform RBAC**. **No procurement-specific roles** are invented
(no "Procurement Administrator", no "Procurement Viewer"). Capabilities are **discrete permissions**
assigned to platform roles. Permission **names are indicative** and may evolve.

| Capability | Permission (indicative) | Typically held by |
|------------|-------------------------|-------------------|
| Workspace View | `procurement.workspace.view` | Purchase Manager |
| Final Quantity Edit | `procurement.final_qty.edit` | Purchase Manager |
| Skip Product | `procurement.product.skip` | Purchase Manager |
| Supplier Assignment | `procurement.supplier.assign` | Purchase Manager |
| Supplier Change | `procurement.supplier.change` | Purchase Manager |
| Pending Finalization | `procurement.pending.finalize` | Purchase Manager |
| Export Generation | `procurement.export.generate` | Purchase Manager |
| Export Approval | `procurement.export.approve` | Purchase Manager / senior (separation of duties) |
| Reports | `procurement.reports.view` | as granted |
| Cycle Create / Close | `procurement.cycle.create` / `.close` | Administration (platform role) |
| Refresh Create / Close | `procurement.refresh.create` / `.close` | Administration (platform role) |
| Rules Manage | `procurement.rules.manage` | Administration (platform role) |

**Business responsibilities:** Normal/Store User → no procurement permissions (no Workspace, no Sync
panel). Purchase Manager → the workspace decision permissions (no cycle/refresh/rules/sync). Administration
→ holds `cycle.*` / `refresh.*` / `rules.manage` via platform RBAC. Sync monitoring → platform permission,
authorized admins only (never Procurement users).

## Access-control decision log (AC-01…AC-04, 2026-06-27)

| ID | Decision | Supersedes |
|----|----------|-----------|
| AC-01 | **No dedicated Procurement Administrator role.** Admin capabilities are **permissions** on platform roles (`procurement.cycle.*`, `procurement.refresh.*`, `procurement.rules.manage`). | Topic-02 gap AC-01 |
| AC-02 | **Discrete business permissions** for each capability (Workspace View, Final Qty Edit, Skip, Supplier Assign, Supplier Change, Pending Finalize, Export Generate, Export Approve, Reports). FDD states responsibilities; names may evolve. | Topic-02 gap AC-02; legacy broad `PURCHASE` perms |
| AC-03 | **No Procurement Viewer role.** Viewing is a permission (`procurement.workspace.view` / `reports.view`). | Topic-02 gap AC-03; legacy `VIEWER` role dropped |
| AC-04 | **Export Generation ≠ Export Approval** — two independent permissions/actions (separation of duties). | Topic-02 Q7 (export create vs approve) |

> Legacy `ROLE_PERMISSIONS` (`SUPER_ADMIN`/`ADMIN`/`PURCHASE`/`VIEWER` with broad perms) is **not
> preserved** where it conflicts with the platform RBAC. The platform permission system is authoritative.

## Open clarifications (non-blocking)

| ID | Topic | Question | State |
|----|-------|----------|-------|
| Q6 | 01 | What business scenarios do legacy `offline_mode` (cycle) and the `PARTIAL` refresh state represent? | Open |
| Q7 | 01 | Should cycle creation / first refresh be gated on confirmed Store Agent sync? | ✅ **Resolved** by PR-BR-021/022/024 — **automatic** sync-gate before cycle creation and every refresh. |

## Pending decisions — Topic 02 (awaiting sign-off)

| ID | Question | Recommendation |
|----|----------|----------------|
| W2-1 | Adopt the spec's **sectioned** workspace as target? Retain legacy **Supplier Queue** as a secondary placement view, or drop it? | Adopt sections; **retain** supplier queue as placement view. |
| W2-2 | Product-first for review, supplier-first for placement — or supplier-first throughout? | Product-first review + supplier-first placement (two phases of one workspace). |
| W2-3 | Keep legacy **top-3 suppliers by frequency + recency** as the suggestion rule? | Keep (detail in Topic 06). |
| W2-4 | Engine considers only **new-GRN delta** (VB) or **full rolling window** each Refresh? | Decide in Topic 03. |
| W2-5 | Confirm Pending lines stay **visible** in workspace (per D2), not auto-hidden once ordered. | Keep visible. |

## Engine decision log — Topic 03 (RATIFIED 2026-06-27)

| ID | Decision | Resolves | Applied in |
|----|----------|----------|-----------|
| E1 | Engine **always uses the Business Cycle Rolling Days** (default 90, configurable); the hard-coded 30 is removed. | W3-1 / C-01 | FDD §8.1/§8.16; PR-BR-001/016; Decision Flow Stage 1–2 |
| E2 | **Max Bill / Max Day Sale are minimum protection floors**, not caps. Final qty = `MAX(coverage, MaxDaySale, MaxBill)` after coverage. | W3-2 / C-02 | FDD §8.5/8.6; PR-BR-007/008/009 |
| E3 | **Required = Target − Effective Available**, where `EffectiveAvailable = CurrentStock + PendingReceivable + ConfirmedInTransit − ReservedQuantity`. | W3-3 / C-03 | FDD §8.10; PR-BR-006/014 |
| E4 | **All classification thresholds are configurable platform parameters** (no hard-coded 50/10/3/15). | W3-4 / C-04 | FDD §8.16; PR-BR-010/011/016 |
| E5 | **Explainability mandatory** — every decision stores Reason Code + Reason Text; excluded products retained. | — | FDD §8.17; PR-BR-015; Decision Flow §3 |

**New documents/rules:** `docs/Procurement_Decision_Flow.md` (engine execution sequence) created;
catalogue expanded — every rule now carries Business Example / Worked Calculation / Intermediate Values /
Final Decision / Reason Code / Displayed Explanation / Decision Explorer Output / Future Dependencies;
new rules **PR-BR-014 (Effective Available)**, **PR-BR-015 (Reason Code & Explainability)**,
**PR-BR-016 (Configurable Decision Parameters)**.

**Still open (non-blocking):** W3-5 — distinct "Monthly Once Sold" rule vs `MovementClass`/frequency
(carry into Topic 04/later).

## Pending decisions — Topic 04 (awaiting sign-off)

| ID | Question | Recommendation |
|----|----------|----------------|
| W4-1 | Migrate legacy `customer_demands` free-text `status` onto the formal 12-state model? In-flight demands to preserve? | Map + migrate; preserve open demands. |
| W4-2 | Is `created_by` the **salesman** and `manager_id` the **reviewing Purchase Manager**? | Confirm role mapping; keep the split. |
| W4-3 | Capture customers by **name + mobile** only, or adopt `CustomerProductMatch.CustomerCode` as canonical customer key? | Use CustomerCode for history where available. |
| W4-4 | Confirm **Demand Type (origin)** is distinct from order `wanted_type` (do not merge). | Keep distinct (C-02). |
| W4-5 | Confirm priority ladder Normal/High/Urgent/Emergency (configurable); orders workspace, never bypasses approval. | Confirm. |

> **Customer Demand = business entity.** FDD §10 extended (10.5–10.13). Catalogue domain added
> (PR-BR-026…035). `CustomerProductMatch` preserved (PR-BR-035). Legacy: capture-only `customer_demands`
> table; **no** lifecycle/priority/type/history/validation/explainability/traceability — greenfield build.
