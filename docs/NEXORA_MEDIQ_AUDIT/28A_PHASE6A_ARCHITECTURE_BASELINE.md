# 28A — Phase 6A Architecture Baseline
**NEXORA MEDIQ — ERP Workspace: Current Architecture Audit and Screen-to-Navigation Mapping**
Date: 2026-11-13
Status: read-only audit. No code changed in this stage.

## 1. Purpose

Phase 6 asks for a unified ERP-style navigation shell, Masters/User Management, configurable Role and Permission Management, Forgot Password, and a dashboard — built on top of whatever already exists. Phase 6's own §6 instruction is explicit: "Inspect existing authorization architecture before implementing a new permission model." This document is that inspection, covering both the frontend navigation/permission surface and the backend auth/role/audit architecture, before any Phase 6B+ implementation begins.

## 2. Frontend navigation architecture (current state)

### 2.1 Structure

A single flat horizontal menubar (`navMenu.jsx`), five fixed groups (`NAV_GROUPS`: Stock, Purchasing, Reports, Tools, Settings), each rendered as either a single button or a dropdown if it has more than one visible screen. No sidebar, no nesting beyond one level, no breadcrumbs, no collapse/expand state, no search. `App.jsx`'s `screens` array (lines 101-119) is the single source of truth for every screen's id/label/group/module tag — 17 entries today:

| id | label | group | module |
|---|---|---|---|
| `stock` | Stock Availability | stock | stock_availability |
| `stock_vertical` | Stock (Vertical) | stock | stock_availability |
| `network_stock` | Network Stock | stock | stock_availability |
| `procurement_workspace` | Procurement | purchase | procurement |
| `order_workspace` | Order Workspace | purchase | order_workspace |
| `order_entry` | Order Entry | purchase | order_entry |
| `legacy_order` | Legacy Order | purchase | legacy_order |
| `sync_live` | Sync Live | tools | sync |
| `analysis` | Supplier Stock Analysis | purchase | supplier_stock_analysis |
| `rate_analysis` | Rate Analysis | purchase | rate_analysis |
| `non_moving` | Non-Moving Stock | purchase | non_moving |
| `nmw_sales` | NMW Sales Report | reports | nmw_sales_report |
| `time_report` | Time Report | reports | time_report |
| `label_exporter` | Label Exporter | tools | label_exporter |
| `whatsapp` | WhatsApp | tools | whatsapp |
| `schema_sync` | Schema Sync | tools | schema_sync |
| `settings` | Settings | system | settings |

### 2.2 The real permission model: ~15 hand-written, role-name-string special cases, not a generic matrix

There is no generic "permission" concept on the frontend today. `App.jsx`'s `navItems` `useMemo` (lines 454-528) is a sequential pipeline of named boolean-gate functions, each checking substring matches against `session.user.roles[].role_name`, applied in a specific, load-bearing order:

`isLabelReviewOnly` → `isStockViewerOnly` → `isStockAndLabelViewer` → `isSmsPurchaseManagerOnly` (each an early-return, full nav replacement) → then, for everyone else: `isSupplierAnalysisBlocked`, `storeWhatsAppAvailable`, `isSalesmanOnly` (gates `nmw_sales`), `isSuperAdmin`/`canViewPurchaseDetails` (gates `order_workspace`/`procurement_workspace`/`rate_analysis`/`order_entry`/`non_moving`), `isSuperAdmin` alone (gates `schema_sync`/`legacy_order`/`sync_live`), a `TIME_REPORT` module-grant check, then a final `modules.includes(screen.module)` fallback for anything not already force-included.

**Each of these is backed by a specific, dated owner ruling and a specific server-side mirror**, not an arbitrary frontend convenience:
- `isSmsPurchaseManagerOnly` → owner ruling 2026-11-12, exactly six screens for the shared SMS tenant login.
- `nmwBlocked`/`nmw_sales` visibility → owner ruling 2026-10-03 ("all branches must see the NMW stock list"); per-product detail drill-down is separately gated server-side in `modules/nmw_sales_report/service.py`'s `_assert_can_view_details`.
- `nonMovingAllowed` → owner rulings 2026-11-01/02.
- `isSupplierAnalysisBlocked` → explicitly documented as mirroring `backend.dependencies.store_scope.is_supplier_analysis_blocked`.
- `schema_sync`/`legacy_order`/`sync_live` → super-admin-only because the APIs themselves are admin-only (schema_sync runs live DDL against production/HO).

**Implication for Phase 6**: these are not placeholder logic to be swept away by a generic permission matrix. Each encodes a specific business decision with a specific backend enforcement counterpart. A "Role and Permission Management" UI must be able to *express* these exact rules (or formally, deliberately migrate them with the same effect), not silently drop or generalize them. Doc 6 §6's instruction to preserve `SMS_PURCHASE_MANAGER` compatibility is the sharpest instance of this — it is one of fifteen such cases, not the only one.

## 3. Backend authorization architecture (current state)

Investigated read-only this phase (see commit for the full agent findings this report distills).

### 3.1 A real, mostly-dormant RBAC schema already exists

Contrary to the premise that permissions are "purely code," a genuine data-driven permission model is already built:
- `dbo.roles` (`role_id`, `role_name`, `description`, `is_active`) — `backend/repositories/role_repository.py`, seeded from a fixed list (`SUPER_ADMIN`, `PLATFORM_OWNER`, `TENANT_ADMIN`, `STORE_ADMIN`, `STORE_MANAGER`, `STORE_USER`, `SYNC_OPERATOR`).
- `dbo.modules` (`module_id`, `module_code`, `module_name`, `is_active`).
- `dbo.role_module_access` (`role_id`, `module_id`, `can_view`, `can_create`, `can_edit`, `can_delete`, `can_export`, `is_active`) — **a real module×action permission matrix**, structurally exactly what Phase 6 §6 asks for. A stored procedure `dbo.sp_RoleModuleAccess_Seed` exists for super-admin seeding.
- `dbo.user_store_roles` — many-to-many, store-scoped user↔role assignment.
- `dbo.users` (includes `active_session_id`/`active_session_at` for an existing single-session enforcement feature).

**The two systems — role-name checks and the module-access matrix — are largely disconnected.** `dependencies/auth.py`'s `has_full_access` and most of `dependencies/store_scope.py` check role-name strings against hardcoded sets/substrings (e.g. `"superadmin" in name`), never consulting `role_module_access`. The one place the real matrix data is actually consulted for an authorization decision (not just display) is `modules/procurement/access.py`'s `grants_procurement_workspace`/`grants_procurement_*`, via `UserRepository.get_user_modules`.

### 3.2 `assert_tenant_access` / `require_procurement_workspace` / `has_full_access` — exact behavior

- **`has_full_access`** (`dependencies/auth.py`): `is_platform_user` OR role name in `{SUPER_ADMIN, PLATFORM_OWNER}`. Hardcoded set, not data-driven.
- **`assert_tenant_access`** (`dependencies/store_scope.py`): `has_unrestricted_scope` (super-admin/platform-user) short-circuits; otherwise exact string comparison of the JWT's `tenant_id` claim against the resource's `tenant_id`. Privilege check is role-name substring matching underneath.
- **`require_procurement_workspace`** (`modules/procurement/access.py`): genuinely different — loads real `role_module_access` rows via `load_module_codes`/`get_user_modules`, checks whether any module code contains `PROCUREMENT`/`PURCHASE`. This is the one existing precedent for a true data-driven permission check.

**Correction/addition to prior audit docs**: docs 07/14/19/21 describe these three correctly for what they check, but none surfaced that a real, largely-unused permission-matrix schema already exists underneath. This is new information, not a contradiction of anything previously stated.

### 3.3 JWT claims

Issued at login (`controllers/auth_controller.py`): `sub` (user_id), `username`, `tenant_id`, `is_platform_user`, `role_names` (list of strings), `store_id`, `store_code`, `sid` (session id). **No permissions/capabilities claim exists** — only role names travel in the token; the module-access matrix is read from the database per-request where it's consulted at all (procurement's access checks), never embedded in the token itself.

One unrelated, pre-existing hardening note surfaced incidentally: `config/security.py`'s `SECRET_KEY` falls back to a literal dev default (`"dev-only-insecure-secret-change-me"`) if `UNINEX_JWT_SECRET` is unset. Not a Phase 6 concern, but worth carrying forward as a general security note — not actioned in this phase.

### 3.4 Existing configurable permission UI/API surface, and its real gap

`GET/POST/PUT/PATCH /api/roles`, `GET/POST/PUT/PATCH /api/users`, and `GET/POST /api/role-module-access/*` **already exist** as backend endpoints — far more is built than Phase 6's framing assumed.

**The critical finding of this phase**: none of these mutation endpoints check any permission beyond the global `require_auth` middleware's "is this a valid JWT at all." `api/app.py`'s `require_auth` middleware does enforce authentication on every `/api/*` path except an explicit public whitelist — these endpoints are not anonymously reachable. But **any authenticated user of any role** — a Salesman, a Stock Viewer — can today call:
- `POST /api/roles` / `PUT /api/roles/{id}` — create or edit any role.
- `PATCH /api/users/{id}/status` — deactivate any user, including the only remaining superadmin (no last-superadmin protection exists anywhere in the codebase).
- `GET /api/users` — list users; `tenant_id` is an optional *filter*, not an enforced boundary, so this also leaks cross-tenant user lists to any logged-in store-level user today.

This is a pre-existing gap, not something Phase 6 or any prior phase introduced — but it is directly in the path of what Phase 6 §5/§6 asks to be built (a user-management and role-management UI on top of exactly these endpoints). Building that UI without closing this gap first would hand every logged-in user superadmin-equivalent backend power through the API, regardless of what the frontend UI chooses to show or hide — directly violating Phase 6 §6's own mandatory rule 4 ("Hidden menus must never be treated as security enforcement").

**Also missing**: no user-role-assignment *mutation* endpoint exists (`user_role_controller.py` has only bulk-seeding endpoints and one read-only `GET /user/{id}`) — Phase 6 §5's "assign permitted roles to a user" has no API to call yet; it would need to be built, not merely wired to.

### 3.5 Password/auth and Forgot Password readiness

- Password hashing: **bcrypt**, correctly used (`bcrypt.hashpw`/`gensalt()` on write, `bcrypt.checkpw` on login) — sound, no change needed.
- **No password-reset flow exists anywhere in the backend today.**
- **No generic transactional-email utility exists.** The only SMTP code in the repository (`modules/sync/file_transfer_transport/email.py`) is a tightly-coupled store↔HO sync-package transport (fixed `NEXORA-SYNC`/`NEXORA-RESULT` subject grammar, zip/json attachments only) — useful as a reference for *how* this project does SMTP (stdlib `smtplib` + STARTTLS, credentials from an env var named by config), but not reusable as-is for a user-facing reset email.
- **No existing secure single-use token utility fits Phase 6's spec directly.** `config/security.py`'s `create_confirmation_token`/`decode_confirmation_token` (JWT-based, 10-minute expiry, used today for Legacy Order's Qty Check confirmation step) is the closest existing pattern — short-lived, signed, audience-scoped — but a JWT's validity is provable from its signature alone, so it cannot be individually revoked/marked single-use without an additional server-side revocation list, which defeats the simplicity Phase 6 §7 asks for ("store only a hash of the token... invalidate on use"). A reset token should be a random secret (e.g. `secrets.token_urlsafe`), hashed and stored, checked against the hash and an expiry/used-flag column — a new, small, purpose-built mechanism, not a reuse of the JWT confirmation-token pattern.

### 3.6 Audit logging — already built, already wired, closest thing to "done" in this entire phase

A complete, mature, append-only audit system already exists: `backend/modules/audit/` — a `dbo.audit_logs` table with immutability guards (raises on any attempted update/delete), 6 indexes each ending in `timestamp DESC`, a `record_audit`/`record_audit_strict` writer, structured `ActorRole`/`AuditCategory`/`AuditStatus` models, before/after diff computation (`compute_mutation_diff`), request-context capture (`AuditContext.from_request`), and a failure-capturing middleware. **Already wired into login success/failure/denial and user/role create/update/status-change** — each call captures actor, target, a computed diff, and (implicitly) timestamp.

This single piece of existing infrastructure already satisfies most of Phase 6 §6's audit requirement ("audit all role and permission changes... record actor, target, timestamp and changed permissions"). Extending it to role-module-access and user-role-assignment mutations (once those mutation endpoints exist) is a matter of copying the existing call pattern from `role_controller.py`, not new design work.

### 3.7 Tenant isolation mechanism

`tenant_id` travels as a JWT claim, set once at login from the user's own database record — never client-supplied on the authenticated path. `assert_tenant_access` compares that claim against a resource's `tenant_id` argument, 403ing on mismatch unless the caller has unrestricted (super-admin/platform) scope. This mechanism itself is sound and was not found to be bypassable anywhere in the Phase-6-relevant surface examined. **It is, however, not applied to `GET /api/users` or `GET /api/roles` at all** (§3.4) — the concrete tenant-isolation gap Phase 6's Masters/User-Management work must close, not a flaw in `assert_tenant_access` itself.

## 4. Screen-to-navigation mapping against Phase 6's proposed hierarchy

Every existing screen mapped to exactly one primary location in Phase 6 §3's proposed structure, adapted to what actually exists (no invented screens):

| Existing screen (`App.jsx` id) | Phase 6 primary location | Notes |
|---|---|---|
| `stock` (Stock Availability) | 03 — Inventory | |
| `stock_vertical` | 03 — Inventory | |
| `network_stock` | 03 — Inventory | |
| `non_moving` | 03 — Inventory | Super-admin / purchase-manager only, unchanged |
| `nmw_sales` | 03 — Inventory *or* 04 — Sales & Reports | Listed as "NMW Sales Report" explicitly under both in Phase 6 §3; placed under Inventory (dispatch-bill nature) with a cross-link from Reports, not duplicated |
| `procurement_workspace` | 02 — Procurement | |
| `order_workspace` | 02 — Procurement | |
| `order_entry` | 02 — Procurement | |
| `legacy_order` | 02 — Procurement | Super-admin only, cross-tenant — unchanged |
| `analysis` (Supplier Stock Analysis) | 02 — Procurement | Admin-tier gate (`isSupplierAnalysisBlocked`) unchanged |
| `rate_analysis` | 02 — Procurement | |
| `time_report` | 04 — Sales & Reports | |
| `label_exporter` | 05 — Tools | |
| `whatsapp` | 05 — Tools | Electron-only availability check unchanged |
| `sync_live` | 05 — Tools | Super-admin only, unchanged |
| `schema_sync` | 05 — Tools | Super-admin only, production-DDL — unchanged |
| `settings` | 06 — Administration | |

**No existing screen is proposed to disappear.** Phase 6 §3's own Masters/Administration categories (User Management, Role Management, Permission Management, Store/Branch Management, Product Masters, Audit Logs, Application Configuration) are **new screens**, not remappings — these do not exist today in any form and are what Phase 6B-6H's actual implementation work builds. Supplier Masters and Product Masters are explicitly flagged by Phase 6 §3 as "do not invent CRUD capabilities for data sources that are currently read-only" — per the audit, supplier/product master data is read from `sync.*` tables (owned by the legacy POS sync pipeline, not this application), so these two Masters entries, if built at all, must be read-only views, not CRUD screens, unless a separate, explicit authorization changes that.

## 5. Summary: what Phase 6 can build on vs. what must be built new

**Can build on directly (exists, sound, just needs a UI and/or minor extension):**
- `dbo.roles` / `dbo.modules` / `dbo.role_module_access` schema — the permission-matrix data model Phase 6 §6 asks for already exists.
- `GET/POST/PUT/PATCH /api/roles`, `/api/users`, `/api/role-module-access/*` — the CRUD surface already exists.
- The audit-log system — already wired into user/role mutations; extending coverage is copy-paste, not new design.
- bcrypt password hashing — sound as-is.
- `secrets`-module-based token generation (stdlib, no new dependency) — the right primitive for Forgot Password, once wired to a new table.

**Must be built new, carefully, before or alongside any Masters/Role-Management UI (Phase 6C/6D):**
- Permission gating on `role_controller.py`/`user_controller.py`/`role_module_access_controller.py`'s mutation endpoints (currently open to any authenticated user — §3.4).
- Tenant-scoping enforcement on `GET /api/users`/`GET /api/roles` (currently unscoped — §3.4/§3.7).
- Last-superadmin protection (does not exist anywhere today — explicitly required by Phase 6 §5/§6).
- A user-role-assignment mutation endpoint (only bulk-seed/read endpoints exist today).
- A password-reset token table + endpoints (nothing exists today) — new, small, purpose-built, per §3.5's reasoning.
- An ERP navigation shell component to replace the current flat 5-group horizontal menubar (§2.1) — ground-up, not incremental.
- A translation layer from the ~15 existing hand-written special-case nav-gate functions (§2.2) into whatever the new permission-driven navigation model becomes, preserving every existing owner ruling exactly.

## 6. Recommendation carried into the next decision point

Given the severity of §3.4's finding — building a role/user-management UI today would expose those unguarded mutation endpoints to every logged-in user, not just admins — the permission-gating and last-superadmin-protection work should be sequenced *before* or *tightly alongside* the Masters/User-Management UI (Phase 6C), not after it, regardless of Phase 6's own stage ordering (which lists 6C before 6D). This is flagged to the project owner as a sequencing decision before further implementation proceeds.
