# NEXORA Platform — Procurement V1

## Business Architecture Specification (Functional Design Document)

> **Status:** Draft for sign-off — Single Source of Truth before implementation
> **Module:** Procurement V1
> **Audience:** Solution Architects, Business Owners, Developers, QA
> **Nature of this document:** Functional Design Document (FDD). It describes *what* the
> Procurement module does and *why*, in business terms. It deliberately contains **no code,
> no SQL, and no API contracts**. Implementation design follows separately, governed by this document.

---

## 1. Document Control

| Item | Detail |
|------|--------|
| Document Title | Procurement V1 — Business Architecture Specification |
| Platform | NEXORA Multi-Tenant Pharmacy Platform |
| Module | Procurement (Decision Engine) |
| Version | 1.0 (Draft) |
| Classification | Functional Design Document (FDD) |
| Supersedes | None — first procurement specification |
| Depends On | Store Management, Store Agent, Sync Engine, Shared Sync Database |

### 1.1 Purpose

This document is the **single source of truth** for the Procurement module. Every business rule,
status, lifecycle, workspace section, and report described here is binding. Implementation must
conform to this document. Where implementation discovers an ambiguity, this document is updated
first, and only then is code written.

### 1.2 How to read this document

- **Concepts** (Business Cycle, Refresh, Pending, Demand) are defined once and reused.
- **Rules** in the Decision Engine are documented one at a time, each with intent, inputs, and effect.
- **Lifecycles** are described as explicit states and transitions.
- Terminology is preserved exactly as used by the business. The Glossary (Section 14) is authoritative.

### 1.3 Guiding Principles (non-negotiable)

1. **This is a pharmacy procurement decision engine, not a generic ERP purchasing module.** Business
   concepts accumulated over years are preserved, not simplified into generic purchasing terms.
2. **Procurement does not own stock.** Stock is owned by the store and synced in.
3. **Procurement does not own purchases.** Purchase entry and GRN happen at the store.
4. **Procurement produces decisions** — what to buy, how much, and from which supplier — and exports them.
5. No warehouse, no central inventory, no concepts that were not requested are introduced.
6. The business is never redesigned to fit a technical convenience.

---

## 2. Executive Summary

The Procurement module converts **synced store reality** (sales history, current stock, purchase
entries, GRN, pending orders, and customer demand) into **actionable procurement decisions**. It
runs at the central NEXORA Platform level, after the Store Agent has synced the required data.

The module is organised around two time containers:

- A **Business Cycle** — a managed procurement planning period that is opened, worked, and closed.
- A **Refresh** — a recomputation of procurement recommendations *inside* a Business Cycle, performed
  as many times as needed as fresh data arrives.

Within a Refresh, the **Procurement Decision Engine** evaluates each product against a documented set
of business rules and routes it into the **Procurement Workspace**, where a manager reviews, adjusts,
skips, assigns suppliers, and finalises. Finalised decisions are **exported** to suppliers. When goods
arrive, store-level **GRN is synced back**, and Procurement performs **GRN Reconciliation** — comparing
what was ordered against what was received, and creating or closing **Pending** quantities accordingly.

Every significant business event is **audited**. Closed cycles become **read-only history**.

---

## 3. Scope and Position in the Platform

### 3.1 In Scope (Procurement V1)

- Business Cycle lifecycle (create → work → close → read-only history).
- Multiple Refreshes within a Business Cycle, with Refresh numbering and Refresh comparison.
- The Procurement Decision Engine and all its rules.
- The Procurement Workspace and its logical sections.
- Skip policies (three modes) and their release conditions.
- Customer Demand intake (raised by salesman) and its appearance in the workspace.
- Pending management (creation, reduction, carry-forward, finalisation).
- Supplier assignment (single, multiple, partial, out-of-stock, reassignment) and export.
- GRN reconciliation of ordered vs received.
- Audit of business events.
- Reporting.

### 3.2 Out of Scope (explicitly not owned by Procurement)

- Stock ownership and stock valuation — owned by the store, synced in.
- Purchase entry and GRN data entry — performed at the store, synced in.
- Supplier master maintenance beyond what is needed to assign and export.
- Accounting, payments, and invoicing.
- Warehouse, central inventory, or stock transfer concepts.

### 3.3 Position in the data flow

```
STORE (source of truth for stock & purchases)
  │  Purchase entry + GRN performed at store
  ▼
STORE AGENT  ──sync──►  SHARED SYNC DATABASE  ──►  NEXORA CENTRAL PLATFORM
                                                        │
                                                        ▼
                                            PROCUREMENT MODULE (this document)
                                              • reads synced sales / stock / purchase / GRN / pending
                                              • produces procurement decisions
                                              • exports orders to suppliers
                                                        │
                                                        ▼
                                            Goods received at store → GRN synced back
                                                        │
                                                        ▼
                                            GRN RECONCILIATION → Pending updated
```

### 3.4 Pre-conditions for Procurement to begin

Procurement work for a store can only begin when **all** of the following are true:

1. Store **purchase entries** for the relevant period are completed at the store.
2. Store **GRN** for received goods is completed at the store.
3. The store has submitted a **Store Completion Notification** (PR-BR-023): the **Last GRN Number**
   and the **Last Sale Bill Number**. Submission signals that operational data entry is complete.
4. The **Store Agent has synced** all required data into the central NEXORA Platform.

Until the required sync is confirmed, the Decision Engine must not be allowed to produce a Refresh that
would be based on stale or partial data. (See Section 8.13, *GRN Validation*, Section 3.6, and Section 5.4.)

### 3.5 Access Control — Permissions on the Nexora Platform RBAC

Procurement is a **restricted business module**, governed by the **existing Nexora Platform
Role + Permission (RBAC) architecture**. Procurement does **not** invent its own roles. The
following decisions are binding (AC-01…AC-04, ratified 2026-06-27):

- **AC-01 — No dedicated "Procurement Administrator" role.** Administration capabilities are granted
  as **permissions** on existing platform roles (e.g. `procurement.cycle.create`,
  `procurement.cycle.close`, `procurement.refresh.create`, `procurement.refresh.close`,
  `procurement.rules.manage`).
- **AC-02 — Discrete business permissions** replace broad permissions: each procurement capability is
  its own permission (below). The FDD defines the **business responsibility**; permission **names may
  evolve** in implementation.
- **AC-03 — No "Procurement Viewer" role.** Viewing procurement is a **permission**
  (`procurement.workspace.view` / `procurement.reports.view`), not a role.
- **AC-04 — Export Generation and Export Approval are separate permissions** (Section 12) — generation
  prepares the export; approval authorizes release.

**Discrete procurement permissions (business capabilities — names indicative):**

| Capability (business responsibility) | Permission (indicative) | Governs |
|--------------------------------------|-------------------------|---------|
| Workspace View | `procurement.workspace.view` | Seeing the Procurement Workspace at all (PR-BR-017). |
| Final Quantity Edit | `procurement.final_qty.edit` | Editing a line's final order quantity. |
| Skip Product | `procurement.product.skip` | Applying a skip policy to a line. |
| Supplier Assignment | `procurement.supplier.assign` | Assigning a line's quantity to supplier(s). |
| Supplier Change | `procurement.supplier.change` | Reassigning / changing a supplier (incl. out-of-stock). |
| Pending Finalization | `procurement.pending.finalize` | Finalising / closing pending quantities. |
| Export Generation | `procurement.export.generate` | Preparing a supplier export (AC-04). |
| Export Approval | `procurement.export.approve` | Authorizing release of a supplier export (AC-04). |
| Reports | `procurement.reports.view` | Viewing procurement reports. |
| Cycle Create | `procurement.cycle.create` | Creating a Business Cycle (administrative). |
| Cycle Close | `procurement.cycle.close` | Closing a Business Cycle (administrative). |
| Refresh Create | `procurement.refresh.create` | Generating a Refresh (administrative). |
| Refresh Close | `procurement.refresh.close` | Closing/superseding a Refresh (administrative). |
| Rules Manage | `procurement.rules.manage` | Configuring Procurement decision rules. |

**Business responsibilities (which permissions naturally group together):**

- **Normal / Store User** — holds **no** procurement permissions; the Workspace is not visible
  (PR-BR-017). Submits only the Store Completion Notification (Section 3.4). No Sync panel (PR-BR-025).
- **Purchase Manager** — holds the **workspace decision** permissions: `workspace.view`,
  `final_qty.edit`, `product.skip`, `supplier.assign`, `supplier.change`, `pending.finalize`,
  `export.generate` and/or `export.approve`, `reports.view` (PR-BR-018). Does **not** hold cycle /
  refresh / rules / sync permissions (PR-BR-018/019/020). No Sync panel (PR-BR-025).
- **Administration** — `cycle.*`, `refresh.*`, `rules.manage` are granted to whichever platform
  role(s) the deployment designates (e.g. Super Administrator / Administrator). This is an
  **assignment of permissions**, not a procurement-specific role (AC-01/PR-BR-019/020).
- **Sync monitoring/manual controls** remain a **platform** permission held only by authorized
  administrative users (PR-BR-025); never exposed to Procurement users.

Key rules:

- **PR-BR-017 — Role-Based Procurement Access.** Procurement is restricted; users without
  `procurement.workspace.view` never see the Workspace.
- **PR-BR-018 — Purchase Manager Responsibilities.** Owns *decisions inside* a Refresh via the discrete
  workspace permissions; never holds cycle/refresh/sync/rule administration permissions.
- **PR-BR-019 — Business Cycle Administration.** `procurement.cycle.create/close` — granted via platform
  RBAC, never bundled into the Purchase Manager responsibility.
- **PR-BR-020 — Refresh Administration.** `procurement.refresh.create/close` — same permission model;
  Purchase Managers do not hold it.

### 3.6 Synchronization Orchestration

**Architecture principle:** *Synchronization is a platform service. Procurement consumes synchronized
data. Procurement never manages synchronization directly.* Business Cycle and Refresh orchestration
**invoke** the Sync service but **do not expose** Sync operations to Procurement users.

- **PR-BR-024 — Automatic Store Synchronization.** Immediately after a Store Completion Notification, the
  platform **automatically** starts Store Agent synchronization. Store users **never** run sync manually;
  it is an internal platform process.
- **PR-BR-025 — Synchronization Visibility.** Sync is infrastructure. **Store Users and Purchase Managers
  have no Sync panel.** Only authorized administrative users may access sync monitoring / manual controls.
  Procurement remains **independent of Sync administration**.
- **PR-BR-021 — Automatic Synchronization Before Refresh.** Every Refresh must run on the latest synced
  data. Refresh generation **never** uses stale data. Orchestrated flow:

  ```
  Create Refresh Request
        ↓
  Automatically trigger Store Synchronization   (Sync service invoked, not exposed)
        ↓
  Wait until synchronization completes successfully
        ↓
  Validate synchronization status
        ↓
  Generate Refresh
        ↓
  Create Procurement Workspace
  ```

- **PR-BR-022 — Business Cycle Creation Workflow.** Cycle creation follows the same synchronization rule
  and **automatically creates Refresh 1**:

  ```
  Create Business Cycle Request
        ↓
  Execute Synchronization
        ↓
  Wait for successful completion
        ↓
  Create Business Cycle
        ↓
  Automatically Generate Refresh 1
        ↓
  Create Procurement Workspace
  ```

  Subsequent Refreshes are created **independently** (each still sync-gated per PR-BR-021).

> **Reconciliation note (supersedes earlier wording):** §5.4 previously stated the first Refresh is a
> *separate, manual* action. Under **PR-BR-022** the **first Refresh is created automatically** as part of
> cycle creation. Cycle creation and every Refresh are **sync-gated** (PR-BR-021/022). The "explicit first
> refresh" idea is retained only in the sense that the manager controls *when the cycle is created*; the
> Refresh itself is auto-generated immediately after a successful sync.

---

## 4. Core Domain Model (Conceptual)

This section names the principal business entities. It is conceptual only — no schema is implied.

| Entity | Description |
|--------|-------------|
| **Business Cycle** | A managed procurement planning period for a store (or store scope). |
| **Refresh** | A numbered recomputation of procurement decisions within a Business Cycle. |
| **Procurement Line** | A single product under consideration in a Refresh, with its suggested quantity, status, and section. |
| **Customer Demand** | A product requirement raised by a salesman on behalf of a named customer. |
| **Pending** | Quantity that was ordered/decided but not yet received; carried and reconciled over time. |
| **Supplier Assignment** | The allocation of a procurement line's quantity to one or more suppliers. |
| **Export** | The act of issuing finalised, supplier-assigned decisions outward. |
| **GRN Reconciliation Record** | The comparison of ordered vs received for a line, with discrepancy classification. |
| **Audit Event** | An immutable record of a significant business action. |

Relationships (conceptual): A Business Cycle contains many Refreshes. A Refresh contains many
Procurement Lines. A Procurement Line may originate from the Decision Engine or from a Customer Demand,
may carry Pending, and may receive one or more Supplier Assignments. GRN Reconciliation links an
exported decision back to received goods.

---

## 5. Business Cycle

> **Ratified Architecture Decisions (applied as target design — Topic 01 sign-off, 2026-06-27):**
> 1. A Business Cycle is **closed explicitly by the Purchase Manager**. A cycle is **never
>    auto-closed**.
> 2. **Pending items do not block cycle closure.** Pending **carries forward** into the next
>    Business Cycle until finalized.
> 3. **Exactly one Refresh may have `CURRENT` status.** Older Refreshes remain immutable history
>    with `SUPERSEDED` status.
> 4. The separation between **Rolling Days (Business Cycle)**, **Min Days (Refresh)** and
>    **Max Days (Refresh)** is preserved.
> 5. **Status values are standardized.** The inconsistent legacy status names and casing are
>    not preserved.

### 5.1 What is a Business Cycle?

A **Business Cycle** is a controlled procurement planning period. It is the top-level container under
which a manager performs procurement for a store. It bounds *which* data is in play, *what* decisions
are taken, and *when* they are considered final. Everything procurement does happens inside a Business
Cycle.

A Business Cycle is not an accounting period and not a sales period. It is a **decision period**: the
window during which the manager is actively deciding what to procure based on the current synced state.

### 5.2 Why it exists

- To give procurement a **defined start and end**, so decisions are not made against an ever-shifting,
  unbounded data set.
- To group multiple **Refreshes** into one coherent planning effort.
- To produce a **frozen, auditable history** once decisions are complete.
- To separate "what we are deciding now" from "what we decided before."

### 5.3 Lifecycle and canonical statuses

Status tokens are **standardized** (upper snake case). The legacy mix of `ACTIVE`/`active` and
`CLOSED`/`completed` is **not** preserved (Ratified Decision 5). A Business Cycle has exactly two
canonical statuses:

| Status | Meaning | Allowed actions |
|--------|---------|-----------------|
| **`ACTIVE`** | The cycle is open; the manager is working it. | Generate Refreshes; work the workspace; assign suppliers; export; manage pending; **close** (explicitly). |
| **`CLOSED`** | The cycle was closed by the Purchase Manager; immutable history. | None that mutate. Read-only, reportable, auditable. |

State transitions:

```
(create) ──► ACTIVE ──explicit close by Purchase Manager──► CLOSED   (terminal, immutable)
```

Rules:

- A cycle is **`ACTIVE` from creation** — there is no separate Draft state. It may hold **zero
  Refreshes** until the first Refresh is generated.
- **At most one `ACTIVE` cycle per store.**
- A cycle is **never auto-closed.** Closure is always an explicit Purchase Manager action
  (Ratified Decision 1).
- `CLOSED` is **terminal and immutable** (Section 5.6).

### 5.4 Creation

- A Business Cycle is created for a defined **store scope** and starts in **`ACTIVE`**.
- **Creation is administrative** — performed only by users holding the **`procurement.cycle.create`**
  permission (granted via the platform RBAC; AC-01). A **Purchase Manager does not hold it and cannot
  create a cycle** (PR-BR-019).
- Creation follows the **sync-gated workflow** (PR-BR-022): execute synchronization → wait for successful
  completion → create the cycle → **automatically generate Refresh 1** → create the Procurement Workspace.
  The cycle is therefore never created on stale data.
- The **first Refresh is generated automatically** as part of creation (PR-BR-022). Subsequent Refreshes
  are created independently and are each sync-gated (PR-BR-021). *(This supersedes the earlier "manual
  first refresh" wording — see Section 3.6.)*
- Creation **never auto-closes any existing cycle.** If the store already has an `ACTIVE` cycle, creation
  is **blocked** until that cycle is explicitly closed (Ratified Decision 1).
- **Rolling Days** is fixed at creation as a property of the cycle (Section 5.7).
- Creation is an audited event (*Cycle Created*).

### 5.4a Administration boundary

Business Cycle management (create **and** close) is governed by the **`procurement.cycle.create`** and
**`procurement.cycle.close`** permissions (PR-BR-019, AC-01) — not a Purchase Manager responsibility.
The Purchase Manager works **inside** the cycle (Section 3.5) but does not open or close it.

### 5.5 Closure

- Closure is an **explicit action by the Purchase Manager**, never automatic (Ratified Decision 1).
- **Pending does not block closure** (Ratified Decision 2). At closure, unreceived **Pending** quantities
  and any open supplier assignments are **carried forward** into the next Business Cycle, where they
  continue until finalized (Section 11).
- On closure the cycle becomes **`CLOSED`** and **immutable**. There is no interim "closing" state — the
  carry-forward is performed as part of the single close action.
- Closure is an audited event (*Cycle Closed*).

### 5.6 Read-only history after closure

- A Closed Business Cycle is **fully read-only**. No Refresh, line, supplier assignment, pending, or
  demand inside it may be altered.
- All Refreshes, the Decision Engine outputs, manual overrides, supplier assignments, exports, and GRN
  reconciliations are preserved exactly as they stood at closure.
- Closed cycles remain fully reportable (Section 13) and auditable (Section 12).
- New procurement work continues in a **new** Business Cycle; unresolved pendings carried forward from the
  closed cycle appear there (Section 11.4).

### 5.7 Planning windows — Rolling Days vs Min/Max Days (separation preserved)

Three distinct planning parameters are **deliberately kept separate** (Ratified Decision 4). They must
not be conflated:

| Parameter | Scope | Set at | Meaning |
|-----------|-------|--------|---------|
| **Rolling Days** | Business **Cycle** | Cycle creation (default **90**) | The trailing **sales-history window** that forms the demand baseline (the "90 Day Average" basis). |
| **Min Days** | **Refresh** | Each Refresh | **Minimum days of stock cover** to maintain — the reorder trigger. |
| **Max Days** | **Refresh** | Each Refresh | **Maximum days of stock cover** to hold — the order ceiling. |

- **Rolling Days** is a property of the cycle and stays constant for that cycle's lifetime.
- **Min Days** and **Max Days** are chosen **per Refresh**, so each Refresh re-parameterizes the cover
  targets without changing the history window. Validation: `Min Days > 0` and `Max Days ≥ Min Days`.

---

## 6. Refresh

### 6.1 What is a Refresh?

A **Refresh** is a single recomputation of procurement recommendations inside a Business Cycle. When a
Refresh runs, the Decision Engine re-evaluates the current synced data and (re)produces the set of
procurement lines and their suggested quantities, routing each into the appropriate Workspace section.

A Refresh is a **snapshot of the decision state at a point in time** within the cycle.

### 6.2 Why multiple Refreshes exist inside one Business Cycle

Procurement is not a single instantaneous act. Within one planning period:

- New **sales** are synced, changing averages and stock cover.
- New **Customer Demands** are raised by salesmen.
- **GRN** arrives for previously exported orders, reducing Pending.
- Suppliers report **out of stock**, forcing reassignment.
- The manager **skips** or **overrides** items.

Each of these changes the right answer. A Refresh lets the manager **re-run the engine against the latest
reality** without losing the history of what the previous run recommended. Multiple Refreshes within one
cycle represent the iterative tightening of decisions as the period progresses.

### 6.3 Refresh numbering

- Refreshes are numbered **sequentially within the Business Cycle**: Refresh 1, Refresh 2, Refresh 3, …
- Numbering is **monotonic and never reused**, even if a Refresh produced no new actions.
- The number is the stable reference used in comparison, audit, and reporting (e.g., "raised in Refresh 2,
  ordered in Refresh 3").

### 6.4 Refresh lifecycle and canonical statuses

Status tokens are **standardized** (upper snake case). The legacy `PROCESSING` / `ACTIVE` / `PARTIAL`
refresh states are **not** preserved (Ratified Decision 5). A Refresh has the following canonical statuses:

| Status | Meaning |
|--------|---------|
| **`GENERATING`** | The Decision Engine is computing this Refresh from current synced data. |
| **`CURRENT`** | The single active Refresh the manager is working. |
| **`SUPERSEDED`** | A newer Refresh exists; this Refresh is now **immutable history** within the cycle. |

Rules:

- **Exactly one Refresh is `CURRENT`** per cycle at any time (Ratified Decision 3).
- Generating a new Refresh marks the previous `CURRENT` as **`SUPERSEDED`** and immutable. The superseded
  Refresh's recommendations, overrides, skips and assignments are **retained** for comparison and audit but
  **cannot be altered**.
- A Refresh begins `GENERATING`; on successful completion it becomes the new `CURRENT`.
- Manager actions (skips, overrides, supplier assignments, demand handling) carry forward into the new
  `CURRENT` Refresh according to their own rules (e.g., a "Skip Until Next Sale" persists; a "Skip Current
  Refresh" is released). See Section 9.
- Refresh generation is an audited event (*Refresh Generated*).

### 6.5 Compare with previous Refresh

Every Refresh (from Refresh 2 onward) supports an explicit **comparison against the previous Refresh** so
the manager can see *what changed and why*, rather than re-reviewing everything. The comparison surfaces,
per product:

- **New** lines that appeared (e.g., a new Customer Demand, or stock fell below Min Days).
- **Removed / Completed** lines that are no longer required.
- **Quantity changed** — suggested quantity went up or down, with the contributing reason.
- **Pending changed** — pending increased (new order) or decreased (GRN received).
- **Status changed** — e.g., moved from Skipped back to Normal because a new sale occurred.
- **Supplier changed** — reassignment since the last Refresh.

This comparison is the operational heart of why Refreshes exist, and is formalised as the **Compare Refresh**
rule in the Decision Engine (Section 8.12).

### 6.6 Refresh administration and sync gating

- **Refresh generation is administrative** (PR-BR-020): only users holding the
  **`procurement.refresh.create`** permission (granted via platform RBAC; AC-01) may generate a Refresh.
  **Purchase Managers do not hold it and cannot generate Refreshes** — they only *work* the resulting
  workspace (Section 3.5).
- **Every Refresh is sync-gated** (PR-BR-021): the request automatically triggers Store synchronization,
  waits for successful completion, validates sync status, and only then generates the Refresh and creates
  the Workspace. A Refresh is **never** built on stale data. (Orchestration flow in Section 3.6.)
- The Sync service is **invoked, not exposed** — no Sync controls appear in the Refresh UI for Procurement
  users (PR-BR-025, Section 3.6).

---

## 7. Procurement Workspace

### 7.0 Access (restricted)

The Procurement Workspace is **restricted** (PR-BR-017): it is **not visible** to Normal/Store Users. The
**Purchase Manager** is the primary workspace operator (PR-BR-018) — reviewing lines, editing Final
Quantity, making Skip decisions, assigning suppliers, applying Manual Overrides, finalising Pending, and
approving Supplier Export. Cycle/Refresh/Sync/rule **administration** is out of the Purchase Manager's
scope (Sections 3.5, 5.4a, 6.6). No Sync panel is shown to workspace users (PR-BR-025).

### 7.1 Purpose

The **Procurement Workspace** is the manager's working surface for the **Current Refresh**. The Decision
Engine routes every procurement line into exactly one **logical section** based on its nature and status.
Sections exist so the manager can attack the highest-value, time-sensitive work first and clearly see what
still needs attention versus what is settled.

A line lives in exactly one section at a time. As the manager acts (or as a new Refresh runs), lines move
between sections according to documented rules.

### 7.2 Logical sections

| Section | What it contains | Why it is separate |
|---------|------------------|--------------------|
| **Customer Demand** | Lines originating from demands raised by salesmen for named customers. | Customer-committed demand is the highest business priority — a real customer is waiting. |
| **High Priority** | Lines the engine flags as urgent (e.g., stock at/below Min Days for fast movers, or strong demand signals). | Stock-out risk on important products must be handled before routine restocking. |
| **Normal Procurement** | Routine restock lines produced by the engine within Min/Max policy. | The bulk of day-to-day procurement; reviewed and assigned in volume. |
| **Pending** | Lines with quantity already ordered/decided but not yet received. | Pending must be tracked separately so it is not re-ordered and is reconciled on receipt. |
| **Skipped** | Lines the manager has chosen to skip under one of the skip policies. | Keeps deliberately deferred items out of the active list while preserving their release conditions. |
| **Manual Review** | Lines the engine cannot decide confidently and routes to a human (e.g., rule conflicts, spikes, anomalies). | Protects against blind automation; forces a human decision where the data is ambiguous. |
| **Completed** | Lines that have been finalised in this cycle (assigned, exported, and/or fully received). | A settled record of what has been actioned. |

### 7.3 Section movement (illustrative)

```
                    ┌──────────────────┐
   Customer Demand ─┤                  │
   High Priority   ─┤  manager works   ├─► assign supplier + export ─► Completed
   Normal          ─┤  the workspace   │
                    └───────┬──────────┘
                            │ skip (one of 3 policies)
                            ▼
                         Skipped ──(release condition met on next Refresh)──► back to its section
                            
   Engine cannot decide ─► Manual Review ─► manager resolves ─► appropriate section

   Exported but not received ─► Pending ─► GRN reconciliation ─► Completed / remains Pending
```

### 7.4 Section behaviour notes

- **Customer Demand** lines never silently disappear; if not procured they must be explicitly skipped,
  marked pending, or completed — a customer is attached.
- **High Priority** is a routing outcome of the engine, not a manual label, although a manual override can
  promote or demote a line (recorded as *Qty Modified* / override audit).
- **Pending** is populated by export/decision and drained by GRN reconciliation; it is never edited by hand
  except through the documented Pending decisions (Section 11.5).
- **Manual Review** must be emptied (resolved) before a cycle can be cleanly closed; unresolved items are
  surfaced during Closing.
- **Completed** is the only section that represents finality within the current cycle.

---

## 8. Procurement Decision Engine

The Decision Engine evaluates each product for a Refresh and computes a **suggested procurement quantity**
and a **section/status**. Each rule below is documented independently: its **intent**, its **inputs**, and
its **effect**. Rules combine; where they conflict, the conflict-handling note applies and, if unresolved,
the line is routed to **Manual Review**.

> The numeric thresholds (e.g., the value of Min Days) are **business-configurable parameters**, not fixed
> constants. This document defines each rule's meaning; the configured values live in platform configuration.

### 8.1 Rolling-Window Average (Cycle Rolling Days)

- **Intent:** Establish a stable demand baseline using the **Business Cycle's Rolling Days** window,
  smoothing short-term noise.
- **Inputs:** Synced sales for the product over the trailing **Rolling Days** window. **Rolling Days is a
  configurable platform parameter set on the Business Cycle; default 90 days** (Section 5.7).
- **Effect:** Produces the rolling-window average consumption, the primary forecasting basis. The Decision
  Engine **must always use the cycle's Rolling Days** — it must **never** use a hard-coded window. *(This
  corrects the legacy engine, which hard-coded 30 days and ignored the cycle parameter — see Topic-03
  analysis. Approved decision 2026-06-27.)*

### 8.2 Daily Average

- **Intent:** Express expected consumption as a per-day rate, so stock cover can be reasoned about in days.
- **Inputs:** Sales history (commonly derived from the 90 Day Average, or a configured window).
- **Effect:** Produces the daily run-rate. Daily Average × target days of cover gives the target stock; the
  gap between target stock and current synced stock drives the suggested order quantity.

### 8.3 Min Days

- **Intent:** Define the **minimum days of stock cover** that must be maintained — the reorder trigger.
- **Inputs:** Daily Average; current synced stock; Min Days parameter.
- **Effect:** When current stock cover (stock ÷ Daily Average) falls **at or below Min Days**, the product
  becomes a procurement candidate. Fast movers crossing Min Days are eligible for **High Priority** routing.

### 8.4 Max Days

- **Intent:** Define the **maximum days of stock cover** to hold — the coverage target.
- **Inputs:** Daily Average; **Effective Available** (Section 8.10); Max Days parameter.
- **Effect:** The coverage quantity is sized to bring cover **up to Max Days**:
  `Target Stock = Max Days × Daily Average`; `Coverage Required = Target Stock − Effective Available`
  (Section 8.10). The **final** quantity is then subject to the **minimum protection quantities**
  (Sections 8.5/8.6), which may raise it.

### 8.5 Maximum Bill Quantity — *Minimum Protection Quantity*

- **Intent:** Guarantee the order can cover a repeat of the **largest single bill** observed.
- **Inputs:** The largest quantity of the product sold on a single bill within the window.
- **Effect:** **Maximum Bill Quantity is NOT a maximum limit. It is a minimum protection quantity (a
  floor).** After the coverage calculation, the final quantity must be **at least** the Maximum Bill
  Quantity. *(Corrected 2026-06-27: earlier wording framed this as a cap; the approved business rule is a
  floor. See Section 8.16 and Topic-03.)*

### 8.6 Maximum Day Sale Quantity — *Minimum Protection Quantity*

- **Intent:** Guarantee the order can cover a repeat of the **largest single-day** demand (spike protection).
- **Inputs:** The maximum quantity sold on any single day within the window.
- **Effect:** **Maximum Day Sale Quantity is NOT a maximum limit. It is a minimum protection quantity (a
  floor).** After the coverage calculation, the final quantity must be **at least** the Maximum Day Sale
  Quantity.

> **Final Quantity rule (8.4 + 8.5 + 8.6).** After computing `Coverage Required = Target Stock − Effective
> Available`, the engine applies the **maximum applicable protection quantity**:
> `Required = MAX(Coverage Required, Maximum Day Sale Quantity, Maximum Bill Quantity)`, then rounds up
> (`CEILING`). The protection quantities can only **raise** the order, never lower it.

### 8.7 Monthly Once Sold

- **Intent:** Correctly handle **slow movers** — products that sell roughly once a month or less — which
  must not be treated with fast-mover restock logic.
- **Inputs:** Sales frequency over the window (occurrences per month).
- **Effect:** Products identified as monthly-once-sold are procured **conservatively** (typically minimal
  cover), or held for **Customer Demand** rather than speculative restock, to avoid dead stock.

### 8.8 Customer Demand

- **Intent:** Ensure explicit, customer-committed demand always reaches procurement, independent of sales-
  history-based forecasting.
- **Inputs:** Demands raised by salesmen (Section 10), each with product and quantity.
- **Effect:** Each demand creates/augments a procurement line and routes it into the **Customer Demand**
  section. Demand quantity is **additive** to (not replaced by) forecast-driven quantity, subject to Pending
  Deduction. A real customer is attached, so the line cannot be silently dropped.

### 8.9 Offer Based Purchase

- **Intent:** Allow procurement to deliberately **buy beyond normal cover** to capture a supplier offer or
  scheme when it is commercially advantageous.
- **Inputs:** Manager indication that an offer applies (and, where relevant, the offer terms).
- **Effect:** The suggested quantity may be **increased above Max Days** under an explicit offer flag. Because
  this intentionally violates the Max Days ceiling, it is treated as a **deliberate override**, audited, and
  attributed to the offer reason.

### 8.10 Effective Available (Pending Deduction)

- **Intent:** Never re-order what is already on hand, on its way, or already committed. Avoid
  double-ordering by sizing against **Effective Available**, not raw current stock.
- **Inputs:** Current Stock; Pending Receivable; Confirmed In Transit; Reserved Quantity.
- **Effect:** The coverage calculation (Section 8.4) uses **Effective Available** in place of current stock:

  ```
  Effective Available = Current Stock
                      + Pending Receivable      (ordered/decided, not yet received)
                      + Confirmed In Transit    (dispatched by supplier, en route)
                      − Reserved Quantity        (already committed/allocated out)

  Coverage Required   = Target Stock − Effective Available
  ```

  *(Replaces the legacy `Target − Current Stock` which ignored pending entirely — approved 2026-06-27.
  Reserved Quantity reduces availability; Pending Receivable and Confirmed In Transit increase it. The
  precise sourcing of each component is finalised in Topic 05 — Pending.)* If Effective Available already
  meets the target, the product is not re-ordered and is shown via the **Pending** section.

### 8.11 Partial Receipt

- **Intent:** Handle the common case where a supplier delivers **only part** of an ordered quantity.
- **Inputs:** GRN received quantity vs the ordered quantity for an exported line.
- **Effect:** The received portion reduces Pending and stock cover updates; the **unreceived remainder stays
  Pending** and carries forward (Section 11). The engine does not re-suggest the already-pending remainder
  (Pending Deduction), but surfaces it for the manager to chase, reassign, or finalise.

### 8.12 Compare Refresh

- **Intent:** Make every Refresh **explainable against the previous one**, so managers act on deltas, not the
  whole list.
- **Inputs:** The current Refresh's lines and the previous Refresh's lines (Section 6.5).
- **Effect:** Produces a per-product **change view**: new, removed/completed, quantity up/down, pending change,
  status change, supplier change — each with the contributing reason. This is the engine's transparency layer.

### 8.13 GRN Validation

- **Intent:** Ensure procurement decisions are based on **received, validated** goods data, and that exported
  orders are reconciled honestly against actual receipts.
- **Inputs:** Synced GRN records for the store; exported decisions awaiting receipt.
- **Effect:** Validates that GRN data is present and consistent before/within a Refresh (a guard supporting
  Section 3.4), and feeds **GRN Reconciliation** (Section 9). Discrepancies (wrong product, extra product,
  extra quantity, incorrect entry — Section 9.2) are flagged for the manager and may route lines to **Manual
  Review**.

### 8.14 Manual Override

- **Intent:** Keep the human in control. The engine **suggests**; the manager **decides**.
- **Inputs:** Manager-entered quantity, supplier, priority, or skip decision on any line.
- **Effect:** A manual override **replaces** the engine's suggestion for that line in the current Refresh and
  is **always audited** (*Qty Modified*, supplier change, etc.) with before/after values. Overrides are
  respected by subsequent rules (e.g., an overridden quantity is still subject to Pending Deduction on export)
  and carried into Refresh comparison so the manager sees that a human decision is in force.

### 8.15 Rule interaction and conflict handling

- Rules are applied to produce a **single suggested quantity and section** per line.
- Forecast rules (8.1–8.4) set the baseline; bound rules (8.5–8.7) constrain it; Customer Demand (8.8) and
  Offer (8.9) add to it; Pending Deduction (8.10) and Partial Receipt (8.11) subtract committed quantity.
- Where rules **materially conflict** (e.g., a spike vs a one-off bulk bill, or demand exceeding sane bounds),
  the engine does **not** guess: the line is routed to **Manual Review** with the conflicting signals shown.
- Manual Override (8.14) always wins for the current Refresh and is audited.

### 8.16 Configurable parameters (no hard-coded thresholds)

All decision thresholds are **configurable platform parameters** (governed by `procurement.rules.manage`),
never hard-coded constants. At minimum:

| Parameter | Scope | Default | Used by |
|-----------|-------|---------|---------|
| Rolling Days | Business Cycle | 90 | Rolling-window average (8.1) |
| Min Days | Refresh | — | Reorder trigger (8.3) |
| Max Days | Refresh | — | Coverage target (8.4) |
| Movement Class cut-offs (Fast / Medium / Slow) | Platform/store | Fast ≥ 50, Medium ≥ 10, Slow > 0 | Movement Class (8.7) |
| Stock Status cut-offs (Low / Safe) | Platform/store | Low cover < 3, Safe cover ≤ 15 | Stock Status routing |

*(The legacy engine hard-coded the Movement/Stock thresholds; these are now parameters — approved 2026-06-27.)*

### 8.17 Explainability — Reason Code and Reason Text (mandatory)

The Decision Engine **must be explainable**. Every product evaluated in a Refresh stores a **Reason Code**
and human-readable **Reason Text** capturing *why* the outcome occurred, so the future **Procurement
Decision Explorer** can answer:

- **Why is this product included?** (e.g., `INCLUDED_BELOW_MIN_DAYS`)
- **Why is this product excluded?** (e.g., `EXCLUDED_NOT_SELLING`, `EXCLUDED_ADEQUATE_COVER`,
  `EXCLUDED_FLAGGED`, `EXCLUDED_INACTIVE`, `EXCLUDED_ZERO_REQUIRED`)
- **Which business rules were evaluated?** (the ordered rule trace — Section: Decision Flow document)
- **Which rule determined the final quantity?** (the **determining reason**: `COVERAGE`,
  `SPIKE_PROTECTION`, or `MAX_BILL_TRIGGER`)

Requirements:

- Each evaluated product persists: **inclusion/exclusion Reason Code**, the **final-quantity determining
  Reason Code**, and a **Reason Text** explanation. Excluded products are also recorded (not silently
  dropped) so exclusions are explainable.
- The complete, ordered execution sequence is defined in **`docs/Procurement_Decision_Flow.md`**.
- Reason Codes are a controlled vocabulary defined in the Business Rule Catalogue (PR-BR-015).

---

## 9. Skip Policies

Skipping lets a manager **deliberately defer** a procurement line without losing it. There are **three skip
modes**, distinguished by the **condition that releases the skip** (i.e., brings the line back into the active
workspace). Skipped lines live in the **Skipped** section and are always audited (*Product Skipped*).

### 9.1 Skip Current Refresh

- **Meaning:** "Not now, but reconsider next time the engine runs."
- **Release condition:** Automatically released on the **next Refresh**. The line re-enters its normal section
  in the next Refresh and is re-evaluated by the engine.
- **Use when:** The manager wants to defer a decision for this pass only (e.g., waiting on more sync data or a
  supplier callback) but expects to revisit it imminently.

### 9.2 Skip Until Next Sale

- **Meaning:** "Don't show this again until it actually sells again."
- **Release condition:** Released only when a **new sale** of the product is synced. Until then it remains
  Skipped across Refreshes.
- **Use when:** A product is currently not moving and the manager does not want to procure it speculatively;
  a fresh sale is the signal that demand has resumed.

### 9.3 Skip Until Next Demand

- **Meaning:** "Don't procure speculatively; only when a customer actually asks for it."
- **Release condition:** Released only when a **new Customer Demand** is raised for the product (Section 10).
  Until then it remains Skipped across Refreshes.
- **Use when:** Slow movers / non-stocked lines that should only be bought against committed customer demand,
  avoiding dead stock.

### 9.4 Skip behaviour summary

| Skip mode | Persists across Refreshes? | Released by |
|-----------|----------------------------|-------------|
| Skip Current Refresh | No | The next Refresh (automatic) |
| Skip Until Next Sale | Yes | A new synced sale of the product |
| Skip Until Next Demand | Yes | A new Customer Demand for the product |

Notes:

- A skip can be **manually released** by the manager at any time (audited).
- Releasing a skip returns the line to the section the engine would route it to in the current Refresh.
- Skips are preserved as **read-only history** when the cycle closes.

---

## 10. Customer Demand

### 10.1 Concept

A **Customer Demand** is a procurement requirement **raised by a salesman** on behalf of a **named customer**.
It represents committed, real demand and is therefore the **highest-priority** input to procurement.

### 10.2 Who raises it

The **salesman** raises the demand at the point the customer asks for a product (typically not in stock, or
needed in quantity). The demand flows into the platform and **appears automatically in the Procurement
Workspace** for the manager.

### 10.3 Mandatory fields

A Customer Demand cannot be raised unless **all** of the following are provided:

| Field | Meaning |
|-------|---------|
| **Salesman** | The salesman raising the demand (accountability). |
| **Customer Name** | The named customer the demand is for. |
| **Mobile** | The customer's contact number (for follow-up when goods arrive). |
| **Remarks** | Free-text context (e.g., urgency, substitution allowed, doctor reference). |
| **Product** | The specific product demanded. |
| **Quantity** | The quantity the customer requires. |

### 10.4 Flow into Procurement

- On submission, the demand **automatically appears** in the **Customer Demand** section of the current
  Refresh's workspace (Section 7.2). No manual import step is required.
- The demand creates or augments a procurement line via the **Customer Demand** rule (Section 8.8); its
  quantity is additive to forecast-driven need, subject to Pending Deduction.
- A demand is an audited event (*Demand Created*).

### 10.5 Customer Demand is a business entity

> **Approved architecture (2026-06-27).** A Customer Demand is **not merely an input** into Procurement.
> It is a **first-class business entity** with its **own lifecycle, status model, priority, type, history,
> validation, explainability and end-to-end traceability** — independent of any single Refresh. A demand
> exists, and is tracked, before, during and after it is included in procurement.

High-level lifecycle:

```
Create → Review → Accepted → Procurement → Ordered → Received → Delivered → Closed
                     │
                     └────────────────► Rejected
```

### 10.6 Demand status model (formal)

Status tokens are standardized (upper-case business states). The set:

| Status | Meaning |
|--------|---------|
| **Draft** | Being captured; not yet submitted. |
| **Submitted** | Raised by the salesman; awaiting review. |
| **Under Review** | Purchase Manager / approver evaluating it. |
| **Approved** | Accepted for procurement (records *why* — §10.10). |
| **Rejected** | Declined (records *why*). Terminal. |
| **Waiting Procurement** | Approved, awaiting inclusion in a Refresh. |
| **Included In Refresh** | Picked up into a Refresh's workspace (traceable to the Refresh). |
| **Ordered** | A supplier order has been placed for it. |
| **Partially Received** | Some of the demanded quantity received (GRN). |
| **Ready For Customer** | Fully received and available for the customer. |
| **Delivered** | Handed to / collected by the customer. |
| **Closed** | Completed and finalised. Terminal. |
| **Cancelled** | Withdrawn before completion (records *why*). Terminal. |

Terminal statuses: `Rejected`, `Closed`, `Cancelled`. Every transition is **audited** with a reason
(§10.10). A demand is never silently dropped.

### 10.7 Demand priority (configurable)

- Priorities are **configurable**; an example ladder: **Normal → High → Urgent → Emergency**.
- **Priority influences workspace ordering** — higher-priority demands surface first in the Customer
  Demand section (Section 7.2) and in the supplier work.
- **Priority never bypasses approval.** An Emergency demand still passes through Review/Approval; priority
  changes *order*, not *governance*.

### 10.8 Demand type (origin)

- A demand records its **origin type**. Examples: **Customer Request, Doctor Request, Hospital Requirement,
  Special Order, Manual Purchase**.
- The type set is **extensible** — future demand types may be added by configuration without redesign.

### 10.9 Customer history (decision support)

When reviewing a demand, the Purchase Manager must **immediately** see, for this customer + product:

- Whether this customer **requested the same product previously**.
- Whether the previous demand was **fulfilled**.
- Whether the previous demand was **cancelled**.
- The **average fulfilment time** for this customer / product.
- **Repeat-request** frequency.

This history informs approval, priority and supplier choices.

### 10.10 Demand validation — no duplicate active demands

- The system **prevents duplicate active demands**. If an **active** demand already exists for the same
  **Customer × Product**, the user is **warned** — duplicates are **never silently created**.
- "Active" excludes terminal statuses (`Rejected`, `Closed`, `Cancelled`). The warning lets the user
  reference/augment the existing demand instead of duplicating it.

### 10.11 Demand explainability

Every demand records the **reason** for each significant decision, and the reason becomes part of the
**audit history**:

- **Why it was approved.**
- **Why it was rejected.**
- **Why it was delayed.**
- **Why it was cancelled.**

These reasons feed the Decision Explorer (§10.13) and the audit trail (Section 14).

### 10.12 Demand → Procurement traceability

Every approved demand must be **traceable end-to-end, navigable in both directions**:

```
Demand → Business Cycle → Refresh → Workspace Item → Supplier Assignment → Supplier Order → GRN → Delivery
```

A user can start from a demand and follow it forward to its delivery, or start from a GRN/order and trace
back to the originating customer demand. Each hop persists the linking identifiers.

### 10.13 Decision Explorer — why a demand did NOT become a procurement item

The Procurement Decision Explorer must also answer **"Why did this Customer Demand not become a Procurement
Item?"**, with a controlled reason set:

`Rejected` · `Duplicate` · `Already Ordered` · `Pending Receipt` · `Skip Until Next Demand` · `Closed` ·
`Cancelled` · `Stock Already Sufficient`.

Each demand not converted in a Refresh stores one of these reasons, so its absence from the workspace is
explainable.

---

## 11. Pending Management

### 11.1 Concept

**Pending** is quantity that has been **decided/ordered/exported but not yet received**. Pending is the
module's memory of "what we are still owed," and it is central to avoiding double-ordering (Pending Deduction,
Section 8.10) and to honest reconciliation against GRN (Section 9 / Section 12 below).

### 11.2 Pending creation

Pending is created when a procurement decision is **committed outward** — i.e., a line is finalised, supplier-
assigned, and **exported** (Section 12.6). The exported quantity becomes Pending for that product/supplier.

### 11.3 Pending reduction

Pending is reduced when **GRN is synced back** and reconciled (Section 12):

- A **full receipt** reduces Pending to zero for that line.
- A **partial receipt** (Section 8.11) reduces Pending by the received quantity; the **remainder stays Pending**.

### 11.4 Pending carry-forward

- Unreceived Pending at the time a **Refresh** is generated **carries forward** into the next Refresh (it is
  not re-ordered, thanks to Pending Deduction).
- Unreceived Pending at the time a **Business Cycle is closed** **carries forward into the next Business Cycle**,
  so nothing owed is lost across the cycle boundary. The originating cycle's record remains read-only history.

### 11.5 Pending finalisation and manager decisions

During the cycle (and especially at Closing), the manager makes explicit decisions on each Pending line:

| Manager decision | Effect |
|------------------|--------|
| **Keep Pending** | Continue to await receipt; carries forward. |
| **Reduce to Received** | Accept the received quantity; close the rest if not expected. |
| **Reassign Supplier** | Move the unreceived remainder to a different supplier (Section 12.5). |
| **Cancel Pending** | The remainder is no longer expected; close it out (audited). |
| **Carry Forward** | Explicitly push the open pending into the next cycle. |

- Closing a pending is an audited event (*Pending Closed*).
- Pending can never be edited as a free number; it only changes through these documented decisions and through
  GRN reconciliation.

---

## 12. Supplier Assignment and Export

### 12.1 Concept

Once the manager has decided **what** and **how much** to procure, the line must be allocated to **suppliers**
and **exported**. Supplier assignment is where a procurement decision becomes an order to a specific supplier.

### 12.2 Single supplier

- The entire quantity of a line is assigned to **one supplier**.
- This is the default, simplest case.

### 12.3 Multiple supplier

- The quantity of a single line is **split across multiple suppliers** (e.g., to balance value, honour offers,
  or because no single supplier can fulfil the whole quantity).
- The sum of supplier allocations must equal the assigned procurement quantity (no over- or under-allocation
  without an explicit manager decision).

### 12.4 Partial quantity

- A supplier may be assigned only **part** of the line's quantity, with the remainder assigned elsewhere or left
  unassigned pending a decision.
- Partial assignment is distinct from **Partial Receipt** (Section 8.11): assignment is about *ordering* intent;
  partial receipt is about *what actually arrived*.

### 12.5 Supplier out of stock and reassignment

- If a supplier reports **out of stock** (before or after export), the affected quantity must be **reassigned**.
- **Reassignment** moves the unfulfilled quantity to a different supplier, or back to the workspace for a fresh
  decision. The previous assignment is retained in history.
- Reassignment is an audited event (*Supplier Changed*).

### 12.6 Export — Generation and Approval (two independent actions, AC-04)

Export is split into **two independent business actions** with **separate permissions** (AC-04):

1. **Export Generation** (`procurement.export.generate`) — **prepares** the supplier export from the
   finalised, supplier-assigned decisions. Generation assembles and stages the export but does **not**
   release it. It produces a generated-but-unapproved export.
2. **Export Approval** (`procurement.export.approve`) — **authorizes release** of a generated export.
   Only on approval is the export considered issued outward to suppliers.

Rules:

- Generation and approval are **distinct steps** and may be held by **different people** (separation of
  duties). A generated export awaits approval; approval cannot occur without a prior generation.
- **Pending is created on release (approval), not on generation** — the approved/exported quantity becomes
  **Pending** (Section 11.2) and the line moves toward **Completed**.
- Both generation and approval are **audited** events. Re-generation or re-approval after reassignment is
  also audited.

### 12.7 Assignment integrity rules

- A line cannot be exported with an unresolved supplier allocation (total assigned must reconcile with the
  decided quantity, or the gap must be an explicit manager decision).
- Out-of-stock and reassignment must always preserve the original intent in history for traceability.

---

## 13. GRN Reconciliation

### 13.1 Concept

After goods are received at the store, store **GRN** is performed and **synced back** to NEXORA. Procurement
then performs **GRN Reconciliation**: comparing what was **ordered/exported** against what was **received**, and
resolving every discrepancy. This is how Pending is honestly drained and how data quality issues are caught.

> Procurement does not perform GRN data entry (that is the store's job) — it **reconciles** the synced GRN
> against its own exported decisions.

### 13.2 Ordered vs Received

For each exported line, reconciliation compares **Ordered Quantity** with **Received Quantity**:

| Outcome | Meaning | Effect |
|---------|---------|--------|
| Received = Ordered | Full receipt. | Pending cleared; line Completed. |
| Received < Ordered | Partial receipt. | Pending reduced by received; remainder stays Pending (Section 8.11). |
| Received > Ordered | Over-receipt. | Flagged as **Extra Quantity** (Section 13.3). |
| Received = 0 | Nothing received. | Full quantity remains Pending; manager chases/cancels/reassigns. |

### 13.3 Discrepancy classifications

Reconciliation classifies anomalies so the manager can act precisely:

| Discrepancy | Meaning | Typical handling |
|-------------|---------|------------------|
| **Wrong Product** | A different product was received than was ordered. | Flag; do not auto-clear Pending; manager decides (accept/return/reorder). |
| **Extra Product** | A product was received that was **not ordered** at all. | Flag for review; does not satisfy any pending order automatically. |
| **Extra Quantity** | More was received than ordered. | Flag over-receipt; manager accepts or returns the excess. |
| **Incorrect Entry** | The GRN data appears mis-entered at the store (e.g., obvious error). | Flag as data quality; route to **Manual Review**; may require re-sync. |
| **Pending after Receipt** | After receipt, a quantity is still owed. | Remainder kept Pending and carried forward (Section 11). |

### 13.4 Reconciliation outcomes

- Clean full receipts move lines to **Completed** and clear Pending.
- Partial receipts and any "Pending after Receipt" keep the remainder in **Pending**.
- Wrong Product / Extra Product / Extra Quantity / Incorrect Entry are **flagged**, may route to **Manual
  Review**, and require an explicit manager decision before the line can be considered settled.
- Every reconciliation action is auditable (receipt, discrepancy flag, pending close).

---

## 14. Audit

### 14.1 Principle

Every **significant business event** in Procurement is recorded as an **immutable Audit Event**, capturing
*who* did *what*, *when*, on *which* cycle/refresh/line, and the *before/after* where a value changed. Audit is
the backbone of trust and of read-only history after closure.

### 14.2 Audited business events (minimum set)

| Event | Captured when |
|-------|---------------|
| **Cycle Created** | A Business Cycle is opened. |
| **Refresh Generated** | A new Refresh is computed within a cycle. |
| **Demand Created** | A salesman raises a Customer Demand. |
| **Product Skipped** | A line is skipped (with which skip policy). |
| **Skip Released** | A skip is released (auto or manual) with the release reason. |
| **Qty Modified** | A manual override changes a suggested quantity (before/after). |
| **Supplier Changed** | A supplier assignment or reassignment occurs (incl. out-of-stock). |
| **Exported** | Finalised decisions are exported; Pending created. |
| **GRN Reconciled** | An ordered-vs-received reconciliation is performed (incl. discrepancy class). |
| **Pending Closed** | A pending quantity is finalised, cancelled, or carried forward. |
| **Cycle Closed** | A Business Cycle is closed and made read-only. |

### 14.3 Audit characteristics

- Audit records are **append-only and immutable** — never edited or deleted.
- Each record ties to its **cycle, refresh, product/line, supplier (where relevant), user, and timestamp**.
- Value changes record **before and after**.
- Audit survives cycle closure unchanged and is fully reportable.

---

## 15. Reporting

The following business reports are required. Each is described by its business purpose (no layout or query is
specified here).

| # | Report | Business purpose |
|---|--------|------------------|
| 1 | **Business Cycle Summary** | Overview of a cycle: refreshes performed, lines procured, exported value/qty, pendings open/closed, outcome. |
| 2 | **Refresh Comparison Report** | Per-product deltas between two Refreshes (new, removed, qty up/down, pending/status/supplier changes). |
| 3 | **Procurement Decision Report** | For a Refresh, each line's suggested qty, the rules that drove it, overrides, and final decision. |
| 4 | **Customer Demand Report** | All demands with salesman, customer, mobile, product, qty, status (raised → fulfilled), and ageing. |
| 5 | **Pending Report** | All open/closed pendings, with ageing, carry-forward history, and current supplier. |
| 6 | **Supplier Assignment / Export Report** | What was assigned/exported to which supplier, including splits and reassignments. |
| 7 | **GRN Reconciliation Report** | Ordered vs received, with discrepancy classifications (wrong/extra product, extra qty, incorrect entry). |
| 8 | **Skipped Items Report** | Skipped lines by skip policy, with release conditions and release history. |
| 9 | **Manual Review Report** | Lines routed to Manual Review, the triggering rule conflict, and resolution. |
| 10 | **Audit Trail Report** | Chronological audit of business events for a cycle (Section 14). |
| 11 | **Slow Mover / Dead Stock Report** | Monthly-once-sold and demand-only products, to guide non-speculative buying. |
| 12 | **Offer Purchase Report** | Lines bought under Offer Based Purchase (above-Max-Days), with the offer reason. |

---

## 16. Glossary

| Term | Definition |
|------|------------|
| **Business Cycle** | A managed procurement decision period for a store scope; created, worked, and closed; read-only after closure. |
| **Refresh** | A numbered recomputation of procurement decisions inside a Business Cycle. |
| **Current Refresh** | The latest, active Refresh in a cycle; the workspace shows this. |
| **Superseded Refresh** | A historical Refresh replaced by a newer one within the same cycle. |
| **Procurement Workspace** | The manager's working surface for the current Refresh, divided into logical sections. |
| **Procurement Line** | A single product under consideration in a Refresh, with suggested qty, status, and section. |
| **Decision Engine** | The rule set that computes suggested quantities and routes lines into sections. |
| **90 Day Average** | Average consumption over the trailing 90 days; primary demand baseline. |
| **Daily Average** | Expected consumption per day; basis for days-of-cover reasoning. |
| **Min Days** | Minimum days of stock cover to maintain; the reorder trigger. |
| **Max Days** | Maximum days of stock cover to hold; the order ceiling. |
| **Maximum Bill Quantity** | Largest single-bill sale quantity; used to cap one-off bulk distortion. |
| **Maximum Day Sale** | Largest single-day sale; used to detect demand spikes/anomalies. |
| **Monthly Once Sold** | A slow mover selling ~once a month or less; procured conservatively or on demand only. |
| **Customer Demand** | A product requirement raised by a salesman for a named customer; highest priority. |
| **Offer Based Purchase** | Deliberate buying above Max Days to capture a supplier offer; an audited override. |
| **Pending** | Quantity ordered/exported but not yet received; carried and reconciled over time. |
| **Pending Deduction** | Subtracting outstanding Pending from new need to avoid double-ordering. |
| **Partial Receipt** | Receipt of only part of an ordered quantity; remainder stays Pending. |
| **Manual Override** | A manager decision that replaces an engine suggestion; always audited. |
| **Compare Refresh** | The per-product change view between the current and previous Refresh. |
| **GRN** | Goods Receipt Note; performed at the store and synced back to NEXORA. |
| **GRN Validation** | Ensuring decisions/reconciliation use present, consistent received-goods data. |
| **GRN Reconciliation** | Comparing ordered vs received and resolving discrepancies. |
| **Skip Current Refresh** | Skip released automatically on the next Refresh. |
| **Skip Until Next Sale** | Skip released only when a new sale of the product is synced. |
| **Skip Until Next Demand** | Skip released only when a new Customer Demand is raised. |
| **Supplier Assignment** | Allocating a line's quantity to one or more suppliers. |
| **Reassignment** | Moving unfulfilled quantity to a different supplier (e.g., out of stock). |
| **Export** | Issuing finalised, supplier-assigned decisions outward; creates Pending. |
| **Manual Review** | Section/state for lines the engine cannot decide confidently; requires human resolution. |
| **Completed** | A line finalised within the cycle (assigned/exported and/or fully received). |
| **Audit Event** | An immutable record of a significant procurement business action. |
| **Store Agent** | The component that syncs store data into the central platform (upstream dependency). |
| **Sync Engine / Shared Sync Database** | Platform components that deliver store data centrally (upstream dependency). |

---

## 17. Appendix A — Consolidated Status Lifecycles

**Business Cycle:** Created → Active → Closing → Closed (Closed = read-only).

**Refresh:** Generating → Current → Superseded (one Current per cycle).

**Procurement Line (section/status):** Customer Demand / High Priority / Normal → (Skipped | Manual Review |
Pending) → Completed.

**Customer Demand:** Raised → In Procurement → Pending → Fulfilled/Completed (or Skipped).

**Pending:** Created (on export) → Reduced (on GRN) → Closed (finalised/cancelled) or Carried Forward.

## 18. Appendix B — End-to-End Narrative (illustrative)

1. Store completes purchase entry and GRN; Store Agent syncs data to NEXORA.
2. Manager **creates a Business Cycle** for the store.
3. Manager **generates Refresh 1**; the Decision Engine evaluates every product and routes lines into the
   workspace sections.
4. Salesmen **raise Customer Demands**; they appear in the Customer Demand section automatically.
5. Manager works the workspace: reviews High Priority and Normal, applies **Manual Overrides**, **skips** some
   lines under the appropriate policy, and resolves **Manual Review**.
6. Manager **assigns suppliers** (single/multiple/partial) and **exports**; exported quantities become **Pending**.
7. New sales and partial GRNs sync in. Manager **generates Refresh 2** and uses **Compare Refresh** to act on
   deltas only. Pending Deduction prevents re-ordering committed quantity.
8. **GRN Reconciliation** runs: full receipts complete lines; partial receipts and discrepancies are handled;
   remainders stay Pending.
9. Manager iterates Refreshes as needed within the cycle.
10. Manager **closes the cycle**: open pendings are finalised or carried forward; the cycle becomes **read-only
    history**. Unresolved pendings appear in the next cycle.

---

*End of Procurement V1 — Business Architecture Specification.*
