# 09 — Security and Tenant Isolation Review

Scope: `backend/modules/legacy_order/router.py`, `backend/modules/procurement/router.py`
and its 8 mounted sub-routers, shared auth/tenant primitives, and the Electron
desktop client (`desktop/supplier-stock-client`). Read-only investigation,
2026-11-13. Tags: VERIFIED (read the exact code), PARTIAL (saw part of the
picture), INFERRED (reasoned from adjacent evidence), UNKNOWN (could not
confirm without running code).

## 1. Shared primitives (ground truth for every row below)

- **`backend/dependencies/auth.py`** — `get_current_user` (`:55`) validates a
  JWT bearer token (signature + expiry via `decode_access_token`) and enforces
  single-active-session (`:32-52`). It does **not** check tenant, store, or
  role. `get_current_user_optional` (`:74`) is the same but tolerates a wholly
  missing bearer token (used for the setup-token read paths). `has_full_access`
  (`:92`) returns true for `is_platform_user` or role in
  `{SUPER_ADMIN, PLATFORM_OWNER}`. VERIFIED.
- **`backend/dependencies/store_scope.py`** — `assert_tenant_access(user,
  tenant_id)` (`:86`) is the ONLY function in the codebase that compares the
  caller's own `tenant_id` claim against a request's `tenant_id` parameter; it
  no-ops for `has_unrestricted_scope` callers (super admin/platform/`user is
  None`). `assert_store_access` (`:94`) is explicitly documented as
  tenant-only, not store-level, by design — Stock Availability/Reports treat
  the tenant, not the store, as the isolation boundary. VERIFIED.
- **`backend/modules/procurement/access.py`** — `require_procurement_admin`,
  `require_procurement_workspace`, `require_procurement_export`,
  `require_procurement_grn` (`:85-110`) are capability-gate FastAPI
  dependencies; they call `has_full_access` first, else load the user's
  module grants from `UserRepository` and 403 if missing, 503 if the lookup
  itself fails ("fail closed"). None of these dependencies call
  `assert_tenant_access` themselves — tenant scoping is a SEPARATE, manually
  added call every route handler must make on its own. VERIFIED. This
  separation is exactly where the gaps below come from: a route can have a
  capability check with no tenant check, a tenant check with no capability
  check, or neither.
- **`backend/api/app.py`** `require_auth` middleware (`:333-360`) is global:
  for every `/api/*` path not in `_PUBLIC_API_PATHS`/`_PUBLIC_AGENT_PATTERNS`,
  it requires a syntactically valid, non-expired bearer JWT (or a scoped
  setup-token on a small GET whitelist). It performs **no claims check beyond
  successful decode** — no role, no tenant, no store. VERIFIED (full function
  read). This means: every router below already requires *some* authenticated
  user of *some* tenant/role; the question for each endpoint is whether it
  additionally confirms that user may see *this* `tenant_id`/`store_id`/
  capability, not whether it requires login at all.

## 2. Procurement module — router-by-router

`backend/modules/procurement/router.py` mounts, in this order: `pipeline_router`,
`orchestration_router`, `pm_router`, `optimization_router`,
`intelligence_router`, `reports_router`, `rules_router`, `vpl_history_router`,
`compare_router`, `vpl_router`, `snapshot_router` (`:33-54`, VERIFIED).

### 2a. `procurement/router.py` itself (cycles CRUD)

| Endpoint | Tenant check | Store check | Permission check | Consistent? | Risk |
|---|---|---|---|---|---|
| `POST /cycles` (`:62`) | none | none | none (no `current_user` param at all) | No | **High** — any authenticated user of any tenant can create a cycle row under an arbitrary `tenant_id` in the body |
| `GET /cycles` (`:67-77`) | `assert_tenant_access` (`:76`) | none (store_id optional, unchecked) | none — `get_current_user_optional` only | Partial | Low-Med — read-only, tenant-gated, but zero capability check (any logged-in user, any role) |
| `GET /cycles/{id}` (`:81-87`) | `assert_tenant_access` (`:86`) | n/a | none | Partial | Low |
| `PUT /cycles/{id}` (`:90-98`) | **none** — no `current_user` param, `tenant_id` only used as a filter | none | none | **No** | **High** — update_cycle has a sibling (`list_cycles`/`get_cycle`) that DOES check tenant; this one silently dropped it |
| `DELETE /cycles/{id}` (`:101-107`) | **none** | none | none | **No** | **High** — same gap, and it's a delete |

Evidence: `create_cycle`, `update_cycle`, `delete_cycle` have no
`Depends(get_current_user*)` parameter whatsoever (`router.py:61-107`
VERIFIED). `list_cycles`/`get_cycle` do. This is an inconsistency within the
same 5-endpoint file, not just across sub-routers.

### 2b. `pm_router.py` — the gold standard

Every one of its ~55 endpoints pairs a capability dependency
(`require_procurement_workspace`/`_admin`/`_export`/`_grn`, or
`get_current_user` for the store-outbox helpers) with an explicit
`assert_tenant_access(current_user, tenant_id)` call on the next line
(VERIFIED by reading the full file, `pm_router.py:56-1194`). Representative:
`workspace` (`:56-89`), `assign` (`:768-779`), `export` (`:823-834`),
`submit_grn` (`:1053-1063`). Distribution run/run-item routes additionally
resolve the owning tenant server-side from the run id before checking
(`distribution_run_detail`, `:684-694`) rather than trusting a client-supplied
`tenant_id` — a stronger pattern than the rest of the module.

**One gap found even here:** `POST /supplier-stock/preview` (`:496-507`) has
**no `current_user` parameter and no tenant check at all** — contrast with its
sibling `POST /supplier-stock/import` two routes down (`:510-527`), which has
both `require_procurement_workspace` and `assert_tenant_access`. Risk: Low
(it only parses an uploaded file and returns a header/sample preview; no
persistence), but it is clearly a missed copy of the same pattern — the kind
of omission `assert_tenant_access`'s own file header ("previously trusted
client-supplied tenant_id with no server check") was written to prevent.
VERIFIED file:line `pm_router.py:496-507` vs `:510-527`.

### 2c. `orchestration_router.py` — mixed

| Endpoint | Tenant check | Permission check | Risk |
|---|---|---|---|
| `POST /cycles/open` (`:20-23`) | none | none (no `current_user` param) | **High** |
| `POST /cycles/{id}/refreshes` (`:26-33`) | none | none | **High** |
| `POST /refreshes/{id}/close` (`:36-41`) | none | none | **High** |
| `POST /cycles/{id}/close` (`:44-51`) | none | none | **High** |
| `POST /stores/{id}/ensure-context` (`:54-65`) | `assert_tenant_access` (`:64`) | `require_procurement_workspace` (`:59`) | OK |

`open_business_cycle` (routed to `create_business_cycle` in
`orchestration_service.py:77-117`) is explicitly documented in its own
docstring as having no real RBAC/tenant check: *"Procurement defines no roles
of its own... Until the auth context is wired into these endpoints, we
require the acting user id; the platform RBAC check plugs in here"*
(`orchestration_service.py:86-89`, VERIFIED). The only gate is that
`created_by` is a non-empty string — any caller can supply any string, it is
never checked against the authenticated identity because there IS no
authenticated identity reaching this function. `create_refresh`,
`close_refresh`, `close_cycle` are the same shape: `tenant_id` is a bare Query
param used only to scope SQL, never validated against a caller. Only
`ensure_context`, added later, got the pm_router-style treatment. **This is
the clearest "newer code regressed the pattern" case in the module** — later
functions in the same file follow the house style; the original three (open/
create_refresh/close) do not.

### 2d. `optimization_router.py` — no auth at all

VERIFIED: the file imports only `fastapi` and `optimization_service`; it does
not import `dependencies.auth` or `dependencies.store_scope` anywhere
(`optimization_router.py:1-16`). Every one of its 8 endpoints
(`optimization`, `apply_moves`, `manual_move`, `audit`, `list_min_orders`,
`set_min_order`, `min_order_config`, `set_consider_minimum_order`) takes
`tenant_id` purely as a `Query(...)` filter with **zero `current_user`
parameter anywhere in the file**. Risk: **High** — `apply_moves` and
`manual_move` mutate live supplier assignments; `set_min_order` mutates a
supplier's Minimum Order Value config. Any holder of a valid JWT for ANY
tenant/role (salesman, purchase manager of a different store, etc.) can move
assignments or rewrite another tenant's minimum-order settings by supplying
that tenant's `tenant_id`.

### 2e. `intelligence_router.py` — no auth at all

VERIFIED: imports only `fastapi`, `pydantic`, `intelligence_service`
(`intelligence_router.py:1-16`). 13 endpoints including 3 mutations
(`build`, `refresh_build`, `assign_supplier_product`) take `tenant_id` in the
body/query with no `current_user` dependency anywhere in the file. Risk:
**High** for the 3 mutations (`assign_supplier_product` writes a supplier→
product mapping across every store in the given tenant); **Medium** for the
10 GETs (cross-tenant read of network procurement intelligence — supplier
offers, per-store sales/purchase history).

### 2f. `pipeline_router.py` — no auth at all

VERIFIED: imports only `fastapi`, `pipeline_service`,
`platform_source_repository` (`pipeline_router.py:1-16`). `POST
/pipeline/run` (`:19-26`) runs the full Sync → Cycle → Refresh → Decision
Engine → VPL pipeline for any `tenant_id`/`store_id` in the body — this is
the single most expensive/impactful write endpoint in the module and it has
**no auth dependency whatsoever**. Risk: **High**. `GET /products/search`
(`:29-37`) is a read with the same gap — Medium.

### 2g. `snapshot_router.py` and `compare_router.py` — no auth at all

Both VERIFIED to import neither `dependencies.auth` nor
`dependencies.store_scope` (`snapshot_router.py:1-13`,
`compare_router.py:1-14`). `snapshot_router`'s `POST /{vpl_id}/snapshot`
and `POST /{vpl_id}/snapshot/{product_id}` recompute and persist per-product
VPL snapshot data for any `tenant_id` passed — Risk **High** (write, no
check). `compare_router`'s `GET /vpl/compare` is read-only cross-VPL diff —
Risk Medium (confirmed cross-tenant read: `compare_service.compare` resolves
both VPLs by the caller-supplied `tenant_id` with no ownership check,
`compare_service.py:17-37` VERIFIED).

### 2h. `vpl_router.py` — split personality

VERIFIED (`vpl_router.py:1-119`): `list_vpls` (`:31-46`) and `get_vpl`
(`:49-56`) DO call `assert_tenant_access` (pattern matches `pm_router.py`).
But `create_vpl` (`:26-28`), `refresh_vpl` (`:59-65`), `generate_vpl`
(`:68-71`), `archive_vpl` (`:74-80`), `delete_vpl` (`:83-85`), `add_product`
(`:92-98`), `list_products` (`:101-109`), `remove_product` (`:112-118`) —
**every mutation and one more read** — have no `current_user` parameter at
all. `delete_vpl` and `generate_vpl` are the standout risks: any authenticated
user can delete or regenerate another tenant's Virtual Product List.

### 2i. `rules_router.py` and `vpl_history_router.py` — consistent, correct

Both VERIFIED to pair `require_procurement_admin` with
`assert_tenant_access` on every tenant-scoped endpoint (`rules_router.py:34-
151`, `vpl_history_router.py:50-193`), matching `pm_router.py`'s house style.
`rules_router.history` (`:54-66`) additionally handles the `tenant_id is
None` super-admin case correctly. No findings here — these are the pattern
the broken routers above should have followed.

### 2j. `reports_router.py` — already fixed once, and the test proves it

`backend/tests/test_procurement_reports_tenant_scoping.py` (VERIFIED, full
file read) documents that `modules/procurement/reports/reports_router.py`
previously had **this exact bug class** — "any logged-in user could pass any
tenant_id and read that tenant's procurement financials" — and was fixed by
adding `get_current_user` + `assert_tenant_access`. This is direct historical
precedent that the bug class recurs in this codebase and has previously
slipped into production before being caught. The fix is covered by 6 tests
(`dashboard`, `store_analysis`, `compare`, plus their 3 Excel-export
siblings) asserting 403 on cross-tenant and success on own-tenant/superadmin.
No equivalent test file exists for `optimization_router.py`,
`intelligence_router.py`, `pipeline_router.py`, `snapshot_router.py`,
`compare_router.py`, `orchestration_router.py`'s three ungated endpoints, or
`vpl_router.py`'s 8 ungated endpoints — meaning the same bug class that was
caught and fixed once in `reports_router.py` is, as of this review, unfixed
and untested in at least 6 other sibling router files. VERIFIED by absence —
no `tenant_scoping` test file references any of those six modules
(`Grep` for `assert_tenant_access`/tenant-scoping test names across
`backend/tests/` and `tests/` returned only the reports file and the two
`pm_router`/`rules_router` auth tests, which test capability, not tenant,
primarily).

## 3. Legacy Order module (`backend/modules/legacy_order/router.py`)

Different model by design (confirmed by its own module docstring,
`router.py:1-9`): this is a platform-ops console over the OLD OrderNMC
database, "gated to super admin / platform users only rather than
tenant-scoped like the rest of the API." The router applies TWO
router-level dependencies to every route (`dependencies=[Depends(
require_order_console_access), Depends(_scope_tenant)]`, `:204-207`,
VERIFIED), so unlike procurement there is no "forgot the dependency on this
one route" risk — the gate is structural, not per-endpoint.

- `require_order_console_access` (`:139-160`) — admins pass; a non-admin
  user is checked against three explicit path-pattern tuples
  (`_VIEWER_READ_PATHS`, `_STORE_WRITE_PATHS`, `_PM_WRITE_PATHS`,
  `:48-98`) AND must own the `{store_name}` path param
  (`_user_owns_store`, `:132-136`, backed by `dbo.user_store_roles`,
  `:105-129`). VERIFIED this is store-level, not just tenant-level —
  tighter than procurement's tenant-only model, appropriate since legacy
  order has no first-class tenant concept of its own.
- `_scope_tenant` (`:172-201`) resolves the ACTIVE SQL Server database
  (OrderNMC vs OrderSMS vs OrderSuccess) from the store name, documented as
  necessary for the post-split multi-tenant HOs. This is tenant routing for
  connection selection, not an access-control check — it doesn't reject
  anything, it just picks which DB to hit. Confirmed this is fine because
  `require_order_console_access` already rejected unauthorized store access
  before this dependency runs.
- A design note worth flagging as **Medium risk / consistency gap**: the
  `_STORE_WRITE_PATHS`/`_VIEWER_READ_PATHS` allow-list is matched by regex
  against `request.url.path`. Every new mutating route added to this router
  must be remembered and added to the correct tuple, or it defaults to
  admin-only (fails closed, so missing it is safe) — but the inverse error
  (a route accidentally added to `_STORE_WRITE_PATHS` with a path pattern
  broader than intended) would fail open silently. No test currently
  enumerates "every route in router.py is in exactly one of these sets or
  requires explicit admin" as an invariant — `test_legacy_order_store_access.py`
  tests `require_order_console_access` in isolation against a handful of
  synthetic paths, not against the live route table. INFERRED gap (no
  evidence of exploitation, but no regression guard either).
- `supplier_match_review`/`supplier_stock_harvest`/`supplier_portal` routes
  all correctly use `require_admin_or_store_pm` (VERIFIED, e.g. `:863-911`),
  consistent with the `_PM_WRITE_PATHS` allow-list.

No cross-tenant/cross-store leak found in `legacy_order/router.py` itself.
The access model is coherent and the one gap (DB health/recovery/sync/stock-
update endpoints requiring only `require_admin` with no finer-grained store
check, e.g. `db_recover` `:219-224`, `start_sync` `:283-291`) is intentional
per the module docstring — these are platform-ops actions, not tenant data.

## 4. Desktop Electron client

- `desktop/supplier-stock-client/electron/main.cjs` — `contextIsolation:
  true`, `nodeIntegration: false` (`:240-248`, VERIFIED); `webviewTag: true`
  is used for Procurement's supplier-portal panel, but `webPanel.attach`
  sandboxes each `<webview>` per its own comment (`:245-247`); the window-open
  handler only allows `http(s)` URLs out to the OS shell (`:252-263`), which
  blocks a malicious `javascript:`/`file:` escape from an untrusted supplier
  page. `export:openPath`/`export:chooseFolder` IPC handlers only accept
  `.xls/.xlsx/.csv` paths or a directory, not arbitrary program execution
  (`:184-203`). PARTIAL — did not read `webPanel.cjs` itself, so cannot
  VERIFY the webview sandbox details beyond the comment at `main.cjs:245`.
- `src/state/session.js` — the bearer token lives in `localStorage`
  (`SESSION_KEY`, `:2, 55-77`), unencrypted, scoped per-day (`loginDate !==
  todayKey()` clears it, `:58`). Standard SPA-token-in-localStorage risk
  (XSS could read it), mitigated somewhat by `contextIsolation`/no Node
  integration in the renderer and by the app being a single-purpose kiosk
  app rather than a general browser. No `httpOnly` cookie alternative is
  used. INFERRED acceptable given the threat model (trusted store PCs,
  not public web), but worth flagging since it's the same token used
  against every endpoint audited above.
- `src/api/client.js` — `authHeaders` (`:9-12`) attaches `Authorization:
  Bearer <token>` from the session object to every request; `request()`
  reads `settings.apiBaseUrl` from `loadSettings()` for the base URL. No
  endpoint call was found that omits the auth header when a session exists
  — VERIFIED by reading the shared `request()` wrapper, which all call
  sites use (confirmed via `ProcurementWorkspace.jsx` call sites, e.g.
  `api.procurementExportDefaults(tenantId, session)` at `:412`, which always
  threads `session` through).
- **Cross-tenant store scoping fix (memory claim) — re-verified, still in
  place.** `tenantId` the client sends is sourced from
  `platformStore?.tenant_id || settings?.tenantId || session?.user?.tenant_id`
  (`ProcurementWorkspace.jsx:280`, VERIFIED) — i.e. from the server-issued
  JWT claims / the store picker the backend already filtered, not a free-typed
  value. The UI itself cannot be used to request another tenant's data. BUT
  — and this is the material point for this review — because the *server*
  endpoints audited in §2c-2h trust the `tenant_id` query param with no
  ownership check, a modified client, a captured request replayed in
  Postman, or any direct API call with a valid JWT from ANY tenant/role can
  still reach another tenant's data through those specific routes. The
  original 2026 fix (desktop client always rendering every tenant) was a
  UI-layer fix; the regression here is server-side and in different,
  newer files than the ones that incident touched.
- **Supplier Analysis warehouse scoping (memory claim) — distinct, correctly
  separate.** `is_supplier_analysis_blocked` (`store_scope.py:63-72`) is an
  admin-only gate independent of tenant/store, layered on top of (not
  instead of) `assert_tenant_access`. This is a different axis (role-based
  tool lock) from the warehouse-store scoping used in Supplier Stock
  Analysis's own router (`backend/modules/supplier_stock_analysis/router.py`,
  not re-read in full this pass — PARTIAL, confirmed only that
  `store_scope.py` exports the right primitive; did not re-walk that
  router's endpoints since it is outside the two modules in scope).
- **Procurement acting-user & GUID handling (memory claim) — verified
  current state.** `access.py:68-70` (`load_module_codes`) and `_require`
  (`:73-82`) key off `current_user.get("sub")`, which is the JWT `sub` claim
  (a user GUID minted at login) — not a client-supplied string. This is
  correctly GUID-based today. The ONE place `created_by`/`editor_id` is
  still a bare, unvalidated string is exactly the `orchestration_service.
  create_business_cycle` gap in §2c — that is not the GUID-mismatch bug
  from the "refresh-500" memory, it's a newer, narrower gap: a present-but-
  unverified identity string, not an absent/non-GUID one.

## 5. Risk summary (narrative)

The procurement module has two authorization layers that must BOTH be
present on every mutating/tenant-scoped route: a capability dependency
(`require_procurement_*`) and a manual `assert_tenant_access` call. There is
no router-level or app-level enforcement that both are present — each
route function must remember to add both. `pm_router.py`, `rules_router.py`,
and `vpl_history_router.py` get this right on every route (and
`reports_router.py` was fixed to match after being caught missing it
entirely). Five sibling files — `optimization_router.py`,
`intelligence_router.py`, `pipeline_router.py`, `snapshot_router.py`,
`compare_router.py` — have **no auth dependency of either kind on any
route**, and `orchestration_router.py` and `vpl_router.py` are split, with
their original/older endpoints missing both checks while newer endpoints in
the same file follow the correct pattern. `procurement/router.py`'s own
`update_cycle`/`delete_cycle` show the same split within one file.

The practical exploit path for all of these: any user who can authenticate
at all (lowest-privilege role, any tenant) can call these endpoints with a
different tenant's `tenant_id` (and, for several, a different `store_id`)
and read or mutate that tenant's cycles, VPLs, supplier assignments,
minimum-order configs, and network procurement intelligence. This is the
same bug class the `reports_router.py` incident already proved happens in
this codebase and already proved is easy to miss without a dedicated test
file per router — which is exactly the gap: no test file exists today for
tenant scoping on any of the six affected routers, only for `reports_router`,
`pm_router` (capability only), and `rules_router` (capability only).

Legacy Order's access model is structurally different and sound: a single
router-level dependency pair enforces admin-or-owns-this-store on every
route, so there is no per-route omission risk the way procurement has. Its
only soft spot is the unenforced invariant that every new write route must
be manually added to the correct path-pattern allow-list, with no test that
walks the live route table to confirm that's actually true.

The Electron client's own token handling, context isolation, and tenant-id
sourcing are sound and match the documented 2026 fix; the client is not the
vector for the gaps found here — the server-side routers are.
