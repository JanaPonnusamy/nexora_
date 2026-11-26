# Master Prompt for Cursor — Continue NexTech MediQ Implementation

Paste everything below this line into Cursor as your task prompt.

---

You are continuing work on **NexTech MediQ**, a new, independent Electron
desktop application at `E:\Nexora\desktop\nextech-mediq`, inside the
larger `E:\Nexora` repository (a pharmacy ERP platform called NEXORA
MEDIQ / UniNex).

**Before doing anything else, read these three files in full, in this order:**

1. `docs/NEXTECH_MEDIQ/IMPLEMENTATION_MASTER_TRACKER.md` — the current
   state of this project: what's built, what's verified, what's not, what
   decisions are locked, what's still open. This is the authoritative
   status document. **Update it at the end of every phase or significant
   chunk of work you complete** — keep its phase-status table, "what
   actually works," "what has NOT been verified," and file list sections
   current. Do not let it drift from reality.
2. `docs/NEXTECH_MEDIQ/01_PHASE1_ARCHITECTURE_DISCOVERY.md` — the
   architecture discovery that justified every design decision made so
   far (why Electron 22 is pinned, why `supplier-stock-client`'s `App.jsx`
   monolith was deliberately NOT copied, what backend API surface exists,
   what branding/naming collisions already existed before this project
   started).
3. `docs/NEXORA_LEGACY_CONSOLIDATION/13_UNKNOWNS_AND_OWNER_DECISIONS.md` —
   relevant **only** once you reach Procurement integration (Phase 8).
   Several business-rule decisions there are still unresolved; do not
   implement Procurement business logic until they're resolved by the
   project owner.

## Non-negotiable constraints (carried over from the original build spec — do not violate these)

- **Never modify, delete, or import-at-runtime any file under
  `desktop/supplier-stock-client/` or `desktop/quick-stock-client/`.**
  Both are existing, operational applications. They may only be *read* as
  reference material. If you think one of them needs a fix, stop and
  report it — do not touch it yourself.
- This is a **third, independent** Electron app. It must build, run, test,
  and package on its own, without either existing client installed.
- **No direct database/SQL access from the Electron renderer, ever.** All
  data comes from the existing FastAPI backend's HTTP APIs.
- **Never invent a new backend endpoint.** If a module needs a capability
  with no existing API, write it down as a missing dependency in the
  tracker file and stop that piece of work — don't guess a contract.
- **Never submit a real supplier order, run a database migration, or
  touch a production database/tenant.** Everything you build is a client;
  business logic and authorization stay server-side.
- Keep the Electron security floor as-is:
  `contextIsolation: true, nodeIntegration: false, sandbox: true` on every
  `BrowserWindow` (see `electron/security/windowDefaults.cjs`). Only loosen
  this with a clearly documented reason, mirroring why
  `supplier-stock-client` sets `sandbox: false` (its webview requirement).
- Keep Electron pinned at **22.3.27** (Windows 7/8 fleet compatibility —
  an explicit owner decision, overriding the original spec's Win10/11-only
  suggestion). Do not upgrade it without checking with the project owner
  first.
- Don't build another `App.jsx` monolith. Keep components small,
  feature-scoped, under `src/modules/<feature>/`. The existing
  `src/modules/stock-enquiry/` folder is the template to follow for shape
  (a page component + a presentational grid component + a service file
  talking to one real backend endpoint + CSS scoped to that module).
- Every navigation entry in `src/navigation/navConfig.js` must have an
  honest `status` (`ready` / `in_progress` / `planned`). Never flip
  something to enabled in the sidebar before its vertical slice actually
  works end-to-end against the real backend.
- Run `npm test` and `npm run build` before considering any phase of work
  done, and actually launch `npm run dev` at least once per phase to
  confirm the app still renders — don't rely on tests alone for an
  Electron app.

## Where this was left off (summary — the tracker file has full detail)

Phases 2-5 are built at a **foundation level** and verified to run, but
**never against a live backend** — only unit-tested with mocked `fetch`.
Specifically:

- Electron main/preload/IPC foundation: done, launches, renders.
- Design system (dark/light/system theme, shell, sidebar, top bar, shared
  loading/empty/error states): done.
- Auth (login/logout wired to the real `/api/auth/login` and
  `/api/auth/logout` endpoints): built, never run against a real backend.
- Stock Enquiry vertical slice (wired to the real
  `/api/stock-availability/products/search` endpoint): built, never run
  against a real backend or a real tenant_id.

## What to do next, in order

1. **First, actually run this against a live/dev backend** and fix
   whatever breaks. This has never happened yet — Phases 2-5 are
   "should work" based on reading the backend source, not "confirmed
   working." Start the backend (check `backend/` for how it's normally
   launched in this repo — look for existing dev-launch docs/scripts
   before inventing your own steps), point `nextech-mediq`'s Settings
   screen at it, log in with a real dev account, and verify Stock Enquiry
   actually returns real data for a real tenant. Fix bugs. Update the
   tracker's "what actually works" section honestly once you've done this.
2. **Phase 6 — Supplier Stock Integration.** Study
   `desktop/supplier-stock-client` in depth (read-only) to find its actual
   Supplier Stock backend endpoints (likely under
   `backend/modules/procurement/supplier_stock_*` and/or
   `backend/modules/legacy_order/supplier_portal.py` /
   `supplier_stock_harvest.py` — there are **two** existing, unreconciled
   implementations per the Phase 7C consolidation investigation; pick
   one or ask the owner which is authoritative rather than merging both
   blindly). Build a new `src/modules/supplier-stock/` module the same
   way Stock Enquiry was built. Write `docs/NEXTECH_MEDIQ/06_PHASE6_SUPPLIER_STOCK.md`
   documenting what you found and built.
3. **Phase 7 — Quick Stock Integration.** Per the original spec: prefer
   native React integration using the real `/api/quick-stock/*` endpoints
   if they're compatible with this app's authenticated-session model; if
   not (Quick Stock today is a PIN-gated, no-login kiosk flow — a
   genuinely different auth model), use a tightly sandboxed, navigation-
   allowlisted embedded surface as an interim measure, never a bare
   unrestricted webview. Write `docs/NEXTECH_MEDIQ/07_PHASE7_QUICK_STOCK.md`.
4. **Phase 8 — Procurement.** Do not start business-logic implementation
   here until you've read and the project owner has resolved the open
   items in `docs/NEXORA_LEGACY_CONSOLIDATION/13_UNKNOWNS_AND_OWNER_DECISIONS.md`.
   If those are still unresolved when you reach this phase, build only
   safe, independent UI/integration scaffolding (navigation entry marked
   `planned`, an empty module folder, nothing that encodes a business
   rule) and stop there, documenting why in
   `docs/NEXTECH_MEDIQ/08_PHASE8_PROCUREMENT_PLAN.md`.
5. **Continue through Phases 9-15** (Inventory/Intelligence,
   Administration, Quality/Performance/Accessibility, Security Validation,
   Testing/Regression, Packaging, Final Release Readiness) in that order,
   each producing its own `docs/NEXTECH_MEDIQ/0N_PHASEN_*.md` report, as
   laid out in the original master build spec. Work autonomously within
   each phase; stop and ask the project owner at any genuine decision gate
   (ambiguous business rule, missing backend capability, a conflict
   between two existing implementations) rather than guessing.
6. **At the end of every phase**, update
   `docs/NEXTECH_MEDIQ/IMPLEMENTATION_MASTER_TRACKER.md`'s status table and
   "what actually works" / "what has NOT been verified" sections to match
   reality, and report back: phase status (COMPLETE/PARTIAL/BLOCKED/FAILED),
   files created/modified, tests run and their results, build result, and
   next-phase recommendation — matching the reporting format in the
   original master build spec's §26.

Do not mark anything "production-ready" or "complete" based on the window
launching alone. Verify against the real backend, run the tests, and be
honest in the tracker file about gaps.
