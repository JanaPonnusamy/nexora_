---
module: Procurement
version: 0.1
status: Draft
owner: Solution Architecture
updated: 2026-06-27
---

# Procurement V1 — Business Analysis

## Topic 04: Customer Demand

> **Method:** Search-first, matching regions only. Code/DB is evidence; the FDD and the Business Rule
> Catalogue are the outputs. The approved Customer Demand architecture (FDD §10.5–10.13) was applied
> **before** this analysis; this topic compares the legacy reality against it.
>
> **Evidence read (Topic 04 only):**
> - Legacy Python: keyword sweep `demand|customer|salesman|wanted|mobile` across `modules/procurements`
>   → **no matching files** (the Python procurement module does not implement Customer Demand).
> - Legacy VB.NET `Form1.vb`: matched regions — `RetrieveDataForOrderDetailsAsync` (ln 1441),
>   `RetrieveDataForOrderSummary` (ln 1468); customer/salesman appear only in **sales** queries (ln 1383–1412).
> - OrderNMC schema: `customer_demands`, `CustomerProductMatch`, `procurement_rows` (demand columns).

---

### 1. Business Summary

A **Customer Demand** is a request for a product on behalf of a named customer. Legacy reality:

- The **VB.NET desktop has no customer-demand entity.** Its "**Wanted / WantedType / WantedDate**" fields
  (on `OrderManagement*` tables) are **order-line classifications** ("what type of order, when wanted"),
  carrying a supplier (`Orsupplier`) and order quantities — **not** a customer with name and mobile.
- The **Python procurement module does not implement demand at all** (no demand files).
- A thin **`customer_demands`** table **does** exist in OrderNMC (customer name, mobile, remarks, product,
  qty, a free-text status, raiser and manager), evidently populated outside the analysed procurement code.

So Customer Demand as the **business entity** defined in FDD §10.5–10.13 (formal lifecycle, status model,
priority, type, history, validation, explainability, traceability) is **essentially greenfield** — only a
minimal capture table exists today.

---

### 2. Current Implementation

**OrderNMC `customer_demands` table (capture only):**

| Column | Note |
|--------|------|
| `id`, `store_id`, `product_id`, `product_label` | identity + product (label allows free product text). |
| `required_qty` | demanded quantity. |
| `customer_name`, `mobile`, `remarks` | the customer + context (matches FDD mandatory fields). |
| `status` (varchar) | **informal free-text** status — no formal model. |
| `created_by`, `manager_id` | raiser and an assigned manager (a review/ownership split exists). |
| `created_at` | timestamp. |

**`procurement_rows` (newer workspace/virtual-items table):** carries `new_customer_demand` (int),
`status`, `order_status`, `wanted_type` — i.e. demands surface into the workspace via a
`new_customer_demand` marker, and rows carry a `wanted_type` order classification.

**`CustomerProductMatch` (31,620 rows):** maps `CustomerCode` → `CustomerProductCode` /
`CustomerProductName` → platform `ProductCode`. A **customer-specific product naming** map — supports
identifying which catalogue product a customer's request refers to, and underpins customer history.

**No stored procedures** exist for demand (`%demand%`/`%wanted%`/`%customer%` → none). **No Python**
procurement code references demand. Capture is via the frontend / another path directly to the table.

**VB.NET:** `RetrieveDataForOrderDetailsAsync` reads `OrderManagementBackup` (`Orqty, OrgOrderQty, remarks,
Wanteddate, WantedType, Orsupplier`) — **order history per product**, not customer demand. Customer/
salesman names appear only in **sales bill** queries (`Sales`, `SalesRep`), unrelated to demand capture.

---

### 3. Business Rules (extracted → catalogued PR-BR-026…035)

| Catalogue ID | Rule |
|--------------|------|
| PR-BR-026 | Customer Demand Entity & Mandatory Fields (customer, mobile, remarks, product, qty, raiser) |
| PR-BR-027 | Demand Status Model & Lifecycle (formal 12-state) |
| PR-BR-028 | Demand Priority (configurable; orders workspace; never bypasses approval) |
| PR-BR-029 | Demand Type / Origin (extensible) |
| PR-BR-030 | Customer History (prior/fulfilled/cancelled/avg time/repeat) |
| PR-BR-031 | Duplicate Active Demand Validation (Customer × Product) |
| PR-BR-032 | Demand Explainability (approve/reject/delay/cancel reasons) |
| PR-BR-033 | Demand → Procurement Traceability (bidirectional chain) |
| PR-BR-034 | Demand Decision Explorer (why demand not converted) |
| PR-BR-035 | Customer Product Match (customer-specific product mapping) — legacy-derived support |

Legacy-confirmed facts feeding these: the capture fields (customer_name/mobile/remarks/required_qty),
the raiser/manager split (`created_by`/`manager_id`), the workspace marker (`new_customer_demand`), and
the customer-product map (`CustomerProductMatch`).

---

### 4. Missing Rules (approved FDD architecture absent in legacy)

- **M-01 — Formal status model.** Legacy `status` is a free-text varchar; the approved 12-state model
  (Draft…Closed/Rejected/Cancelled) is absent.
- **M-02 — Lifecycle transitions & terminal states.** No enforced Create→Review→…→Closed flow.
- **M-03 — Priority** (Normal/High/Urgent/Emergency) — absent. No workspace ordering by priority.
- **M-04 — Demand Type / origin** (Customer/Doctor/Hospital/Special/Manual) — absent (`wanted_type` is an
  order classification, not demand origin).
- **M-05 — Customer history view** (prior same-product, fulfilled/cancelled, avg fulfilment time, repeats)
  — not aggregated; only the raw `CustomerProductMatch` map exists.
- **M-06 — Duplicate active-demand validation** — absent; nothing prevents duplicate Customer × Product.
- **M-07 — Explainability reasons** (approve/reject/delay/cancel) — absent.
- **M-08 — Traceability chain** Demand→Cycle→Refresh→Workspace→Assignment→Order→GRN→Delivery — absent
  (only `product_id`/`store_id` link; `new_customer_demand` is a flag, not a full chain).
- **M-09 — Decision-Explorer "why not converted"** — absent.

### 4b. Extra / legacy-valuable

- **X-01 — `CustomerProductMatch`** (customer-specific product naming, 31,620 rows) — a genuinely useful
  asset for matching a customer's wording to the catalogue and for history; **preserve** (PR-BR-035).
- **X-02 — Raiser/Manager split** (`created_by` / `manager_id`) — aligns with salesman-raises /
  manager-reviews; **preserve** and formalise into the status model.

---

### 5. Conflicts

| # | Conflict | Detail | Action |
|---|----------|--------|--------|
| C-01 | **Informal vs formal status.** | `customer_demands.status` is free-text; approved model is a 12-state vocabulary. | Standardize to the formal model (consistent with the platform status-standardization principle). |
| C-02 | **"Wanted" overloading.** | VB/`OrderManagement` "Wanted/WantedType" is an **order classification**, not customer demand; `procurement_rows.wanted_type` reuses the term. | Keep **Customer Demand** distinct from "Wanted"; do not conflate demand *type* (origin) with order *wanted_type*. |
| C-03 | **Capture-only table vs full entity.** | `customer_demands` lacks priority, type, history, reasons, traceability. | Extend additively per FDD §10.6–10.13 (no redesign of existing fields). |
| C-04 | **Demand origin of `new_customer_demand`.** | Demands surface via a flag/int on `procurement_rows`, not a traceable link. | Replace the flag with a proper Demand→Refresh→WorkspaceItem link (PR-BR-033). |

---

### 6. Recommended Design (documentation-level, no code)

1. **Adopt the approved Customer Demand entity** (FDD §10.5–10.13) as target; treat the legacy
   `customer_demands` table as the **capture nucleus** to be extended (status model, priority, type,
   reasons, trace links) — additively, preserving customer_name/mobile/remarks/required_qty.
2. **Formalise the status model** (PR-BR-027) and map legacy free-text `status` values onto it during
   migration; keep `created_by` = raiser (salesman), `manager_id` = reviewing Purchase Manager.
3. **Preserve `CustomerProductMatch`** as the backing for **Customer History** (PR-BR-030) and for
   resolving a customer's product wording to the catalogue at capture time (PR-BR-035).
4. **Keep Demand Type (origin) separate from order `wanted_type`** to avoid the C-02 overload.
5. **Implement duplicate-active validation** (PR-BR-031) at capture: warn on existing active
   Customer × Product demand.
6. **Persist the full traceability chain** (PR-BR-033) and the Decision-Explorer "why not converted"
   reasons (PR-BR-034), consistent with the engine explainability (PR-BR-015).

---

### 7. Questions (for business owner sign-off)

1. **Migration of legacy `customer_demands`:** map existing free-text `status` values onto the new
   12-state model? Are there in-flight demands to preserve?
2. **Raiser identity:** is `created_by` the **salesman**, and `manager_id` the **reviewing Purchase
   Manager**? Confirm the role mapping.
3. **Customer identity:** customers are captured by **name + mobile** only (no customer master)? Should
   `CustomerProductMatch.CustomerCode` become the canonical customer key for history?
4. **Demand Type vs `wanted_type`:** confirm these are different concepts (origin vs order
   classification) and must not be merged.
5. **Priority ladder:** confirm Normal/High/Urgent/Emergency (configurable) and that priority orders the
   workspace but never bypasses approval.

---

*Topic 04 complete (analysis). Catalogue rules PR-BR-026…035 added. Next in order: **Topic 05 — Pending**
(keywords: pending, received, partial, transit) — which also finalises the Effective Available components
(PR-BR-014) referenced by the engine.*
