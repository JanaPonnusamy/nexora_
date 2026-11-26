# 10 — Recommended Final Architecture
**NEXORA MEDIQ Unification — Phase 0 Audit**

## Summary recommendation

Keep the existing architecture almost entirely intact. There is no case, based on this audit, for a rewrite or a genuine "merge" — the system is already one Electron app with one backend. The recommended end state is a **rebrand + reorganize + selectively extend** of what exists, not a new system.

## Recommended final shape

**Desktop app:** `desktop/supplier-stock-client` (rename product identity only — directory path can stay, or be renamed in a later, separately-approved step if desired for clarity; not required).
- Electron main/preload architecture unchanged: `contextIsolation: true`, `nodeIntegration: false`, no DB/credential exposure to renderer, auto-update ownership unchanged (`NexoraStockClientWatchdog`, SHA-256 + Ed25519 verified packages) — coordinate naming only.
- Frontend: React, decomposed so Order Workspace is its own module (parallel to `ProcurementWorkspace.jsx`), navigation sourced from the existing `screens` data array but rendered through a sidebar instead of menubar dropdowns, with a small shared component library layered on top incrementally.
- Backend: FastAPI, unchanged module boundaries (`backend/modules/procurement/`, `legacy_order/`, etc.), unchanged tenant/role enforcement pattern (`require_*` + `assert_tenant_access`), extended only with genuinely new endpoints for whichever AI Intelligence Centre capabilities get approved and built in Phase 5.
- Branding: "NEXORA MEDIQ — Intelligent Pharmaceutical Workspace" across window title, installer, logo, in-app header.

**Out of scope, left exactly as-is:** `desktop/order-management-client` — a separate, intentionally frozen, remote-access-only legacy tool with its own build pipeline. No shared surface with the main app beyond the backend API it already calls.

## Module structure (final recommendation, reconciling master prompt §4 with what exists)

| Nav group | Contains |
|---|---|
| Dashboard | New screen (Phase 4), built from existing data endpoints |
| Inventory Intelligence | Stock Availability, Stock (Vertical), Network Stock, Non-Moving Stock |
| Procurement Workspace | Procurement, Order Workspace (post-extraction), Order Entry, Legacy Order |
| Supplier Intelligence | Supplier Stock Analysis, Rate Analysis, Web Panel (supplier portals), Supplier WhatsApp |
| Purchase Management | GRN/pending-adjust views, kept as a section within Procurement rather than a forced top-level split (shared backend/data) |
| Sales & Reports | NMW Sales Report, Time Report, Label Exporter, abnormal-sales review |
| AI Intelligence Centre | Shelf-sort classifier (existing) + whatever Phase 5 adds, each clearly labeled verified-data vs. AI-generated |
| Tools | Sync Live, Schema Sync, WhatsApp (store-level) |
| Settings & Administration | Settings screen (scope to be confirmed in Phase 1) |

## Why not a bigger architectural change

- Security model already meets the master prompt's requirements (`07_SECURITY_AND_TENANT_AUDIT.md`) — no redesign needed there.
- Business logic (purchase calculations, supplier matching, stock/sales calculations) lives entirely in the backend and is untouched by any UI-layer work — satisfies master prompt §7 by construction, not by extra effort.
- The one real architectural debt — `App.jsx` entangling Order Workspace with navigation/Procurement — is addressed by a targeted extraction (Phase 3), not a rewrite.

## Final note on AI honesty

The recommended architecture keeps AI capability where it actually is today (one classifier, clearly gated by `llm_available`) and treats every other proposed AI feature as a tracked, separately-approved backlog item — not something the rebrand or redesign should imply already exists.
