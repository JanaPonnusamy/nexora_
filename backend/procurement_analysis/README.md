# Nexora Procurement Engine — Legacy Procurement Intelligence Extraction (LPIE)

**Phase 1 — Reverse Engineering & Documentation (NOT a rebuild).**

## Charter

The existing **VB.NET Procurement Application** has run successfully for years. This phase
**discovers and documents** every business rule, workflow, calculation, configuration, limitation
and hidden assumption in the legacy system. We will **redesign later — not copy**.

The output of this phase becomes the **official Procurement Functional Design Document (FDD)** for Nexora.

## Hard rules (apply to every document here)

- ❌ DO NOT redesign, optimize, or change any workflow.
- ❌ DO NOT generate new business rules or infer behaviour without evidence.
- ✅ ONLY extract **facts** from the legacy system.
- ✅ Every documented behaviour must be **traceable to evidence** (file + line, table, SP, screen, or
  captured SQL). Record it in the `Evidence Source` field and in `evidence/evidence_log.md`.
- These are **templates for incremental population** — fill them as analysis proceeds; do not delete the
  field prompts.

## Legacy sources (read-only references)

| Source | Location |
|--------|----------|
| VB.NET Procurement App | `D:\VBDOTNET\OrderManagement\OrderManagement` |
| Legacy Python (ProcureX) | `D:\NEXORA\backend\modules\procurements`, `D:\NEXORA\frontend\src\apps\procurex-ui` |
| OrderNMC database | SQL Server `OrderNMC` (business reference only — **no modifications**) |

## Folder structure

```
backend/procurement_analysis/
├── README.md                ← this file
├── database/                ← schema inventory, ERD, table classification
├── queries/                 ← READ-ONLY metadata-extraction scripts (no DB changes)
├── screens/                 ← one document per legacy screen (template provided)
├── workflows/               ← one document per operation/workflow (template provided)
├── business_rules/          ← Business Rule Catalog + per-rule template + categories
├── reports/                 ← one document per report (template provided)
├── exports/                 ← export/format analysis (CSV/Excel/supplier/text)
├── configuration/           ← settings, options, thresholds, flags, toggles
├── dll_analysis/            ← assembly/namespace/class/method/form/enum/resource analysis
├── runtime/                 ← captured runtime SQL (operation → query → tables)
├── fdd/                     ← the Procurement FDD skeleton (01–14), populated incrementally
└── evidence/                ← evidence log + traceability index (the backbone of this phase)
```

## How to populate

1. For each artifact (screen, workflow, rule, report, export, table) copy the relevant `_TEMPLATE_*`
   file (or add a row to the relevant catalog) and fill every field.
2. Put the **evidence reference** in the document **and** add a line to `evidence/evidence_log.md`.
3. As facts are confirmed, fold the verified content into the matching `fdd/` section.
4. Status values across all templates: `Empty` → `Draft` → `Evidenced` → `Verified`.

## Status legend

| Status | Meaning |
|--------|---------|
| `Empty` | Template only; no content yet. |
| `Draft` | Content captured, evidence not yet attached. |
| `Evidenced` | Content backed by a specific evidence reference. |
| `Verified` | Cross-checked against a second source / runtime capture. |

> Scope guard: this folder contains **only documentation and read-only extraction scripts**. No procurement
> engine code, no APIs, no UI, and no database modifications are produced in this phase.
