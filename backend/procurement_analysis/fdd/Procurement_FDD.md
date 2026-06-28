---
module: Procurement
document: Functional Design Document (Legacy-derived, LPIE Phase 1)
status: Skeleton
owner: Solution Architecture
updated: 2026-06-27
---

# Nexora Procurement — Functional Design Document (FDD)

> **This is the official Procurement FDD skeleton**, populated incrementally from the LPIE analysis.
> Each section is filled from the verified artifacts in `../` (database, screens, workflows,
> business_rules, reports, exports, configuration, dll_analysis, runtime). **Facts only**, every claim
> traceable to `../evidence/evidence_log.md`. Section status: `Skeleton` → `Drafting` → `Evidenced` →
> `Verified`.

## Section status tracker

| # | Section | Status | Primary sources |
|---|---------|--------|-----------------|
| 01 | Introduction | Skeleton | README, charter |
| 02 | System Overview | Skeleton | dll_analysis, screens |
| 03 | Modules | Skeleton | dll_analysis, screens |
| 04 | Workflows | Skeleton | workflows/ |
| 05 | Business Rules | Skeleton | business_rules/ |
| 06 | Calculations | Skeleton | business_rules/, runtime/ |
| 07 | Reports | Skeleton | reports/ |
| 08 | Export Formats | Skeleton | exports/ |
| 09 | Configuration | Skeleton | configuration/ |
| 10 | Database | Skeleton | database/ |
| 11 | Security | Skeleton | screens/, dll_analysis/ |
| 12 | Known Limitations | Skeleton | all |
| 13 | Missing Features | Skeleton | all |
| 14 | Improvement Opportunities | Skeleton | all (forward-looking, clearly flagged) |

---

## 01 Introduction
- Purpose of this FDD; scope of the legacy procurement system; intended audience.
- Phase note: **as-is reverse engineering** (LPIE), not a redesign.
- Glossary pointer.

## 02 System Overview
- What the legacy procurement application is and does (observed).
- High-level context: store data → procurement decisions → supplier orders.
- Technology footprint (VB.NET app, OrderNMC DB) — facts from `dll_analysis/`, `database/`.

## 03 Modules
- Enumerate functional modules/screens discovered (from `screens/` and `dll_analysis/`).
- For each: one-line purpose + link to its screen document.

## 04 Workflows
- Each documented workflow (from `workflows/`): start → action → DB change → validation → result.
- Include exception/rollback behaviour as observed.

## 05 Business Rules
- Consolidated from `business_rules/business_rule_catalog.md`, by category (Stock, Supplier, Purchase,
  Sales, Pending, Expiry, Batch, Order, Approval, Export, Security).
- Each rule referenced by `LR-<CAT>-NNN` with evidence.

## 06 Calculations
- Every formula discovered (order quantity, averages, days cover, protection floors, pending, etc.),
  quoted from source with evidence and worked examples.

## 07 Reports
- Each report from `reports/`: purpose, filters, grouping, sorting, calculations, output format.

## 08 Export Formats
- Each export from `exports/`: format, encoding, delimiter, column mapping, supplier-specific rules.

## 09 Configuration
- Settings, company/supplier options, calculation parameters, thresholds, flags/toggles, hard-coded
  constants — from `configuration/`.

## 10 Database
- Schema inventory (tables/columns/keys/constraints/indexes/views/SP/functions/triggers) from
  `database/`, plus ER documentation and procurement table classification.

## 11 Security
- Access control as observed (logins, roles, screen/permission gating), session handling, any
  credential handling — from `dll_analysis/`, `screens/`.

## 12 Known Limitations
- Concrete limitations observed in the legacy system (with evidence). Facts, not opinions.

## 13 Missing Features
- Capabilities absent in the legacy system that the business relies on via workarounds (evidence of the
  workaround).

## 14 Improvement Opportunities
- **Forward-looking only — clearly flagged as NOT part of the as-is record.** Candidate improvements for
  the future redesign, each linked to the limitation/missing-feature that motivates it.

---

## Appendix A — Evidence index
Pointer to `../evidence/evidence_log.md` (the master traceability list).

## Appendix B — Open questions
| # | Question | Section | Raised from | Status |
|---|----------|---------|-------------|--------|
