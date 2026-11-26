# Existing-Client Separation — Final Report

Date: 2026-11-14
Branch: `nexora-mediq-implementation`

## 1. Corrected understanding of repository state

The earlier framing of this task (treating the MediQ/NexTech-named files inside
`desktop/supplier-stock-client/` as "contamination" that leaked in from the new
`desktop/nextech-mediq/` project) was **wrong** and has been retracted. The
user confirmed the real situation:

- `desktop/supplier-stock-client` is itself mid-rebrand, from "Axythic Supplier
  Stock" to "NexTech MediQ" / "NEXORA MEDIQ" branding. This is **sanctioned,
  deliberate, ongoing work**, not an accident.
- Commit `960b3a5` — `rebrand(desktop): Axythic Supplier Stock -> NEXORA MEDIQ`
  — is the first landed phase of this rebrand.
- `docs/NEXORA_MEDIQ_AUDIT/24_PHASE5_REBRANDING_AND_WATCHDOG_REPORT.md`
  documents a later phase of the same multi-phase rebrand effort.
- The current uncommitted working-tree changes in `supplier-stock-client/`
  (modified `nexora-mediq-mark.svg`, new `nextech-mediq-lockup.svg`,
  `nextech-mediq-lockup-dark.svg`, `nextech-mediq.ico`, and the `App.jsx`/
  `package.json` edits that reference them) are the **next increment of that
  same sanctioned rebrand**, not stray or misplaced files.

**No files were reverted, undone, or deleted as part of this task.** The
in-progress rebrand in `supplier-stock-client` was left exactly as found,
uncommitted, untouched.

## 2. Three apps' identities

| | supplier-stock-client | quick-stock-client | nextech-mediq |
|---|---|---|---|
| `name` | `nexora-supplier-stock-client` | `nexora-quick-stock-client` | `nextech-mediq` |
| `version` | 0.1.72 | 1.0.0 | 0.1.0 |
| `appId` | `com.nexora.desktop.stock` | `com.nexora.desktop.quickstock` | `com.nextech.mediq.desktop` |
| `productName` (build) | NexTech MediQ | NexTech Quick Stock | NexTech MediQ |
| Electron `main` | `electron/main.cjs` | `electron/main.cjs` | `electron/main/index.cjs` |
| Preload | (in `electron/`, flat) | (in `electron/`, flat) | `electron/preload/index.cjs` (own dir) |
| Renderer | React (Vite) | none (plain HTML/JS) | React (Vite) + react-router-dom |
| Vite `build.outDir` | `dist` | — (no vite) | `dist` |
| electron-builder `directories.output` | `release` | `release` | `release` |
| Install artifact name | `NEXORA-MEDIQ-Setup-${version}` | `NexTechQuickStock-Setup-${version}` | `NexTechMediQ-Setup-${version}` |
| Icon | `src/assets/nextech-mediq.ico` | (none specified) | `src/assets/branding/icon.ico` |

All three `appId`s are distinct (`com.nexora.desktop.stock` /
`com.nexora.desktop.quickstock` / `com.nextech.mediq.desktop`) — confirmed,
no collision.

Note: `productName` is "NexTech MediQ" for **both** supplier-stock-client and
nextech-mediq. This is a cosmetic/display-name duplication, not a structural
collision — `appId` (which Windows/NSIS/electron-builder use for install
identity, registry keys, and update channels) differs, and each app's
`directories.output: "release"` resolves to a separate physical path because
each `package.json` lives in its own project folder
(`desktop/supplier-stock-client/release/` vs `desktop/nextech-mediq/release/`).
Flagged under Remaining Risks below since a human seeing two apps both named
"NexTech MediQ" in Start Menu / Programs could be confused — that is a product
decision for the user, not something this task should resolve unilaterally.

## 3. Asset-overlap finding (Step 1)

Checked with:
```
grep -rn "nextech-mediq" desktop/supplier-stock-client/src desktop/supplier-stock-client/electron desktop/supplier-stock-client/index.html desktop/supplier-stock-client/package.json
```

Result — all three files are **actively referenced by supplier-stock-client's own code**:

- `desktop/supplier-stock-client/src/App.jsx:4-5` imports
  `./assets/nextech-mediq-lockup.svg` and `./assets/nextech-mediq-lockup-dark.svg`
  directly into the renderer.
- `desktop/supplier-stock-client/package.json:55` sets
  `"icon": "src/assets/nextech-mediq.ico"` as the NSIS installer icon.

**Conclusion: case (a) applies.** These are supplier-stock-client's own new
brand assets for its in-progress rename — they belong to supplier-stock-client's
own identity, not to `nextech-mediq`'s. **No files were copied, moved, or
deleted.** `desktop/nextech-mediq/src/assets/branding/` already has its own
independent, complete asset set (`icon.ico` + `icons/`, `png/`, `svg/`
subfolders with 5 lockup variants + README) — there is no gap to fill and no
dead weight to relocate. The two asset sets are coincidentally similarly named
(both projects are becoming "NexTech MediQ") but are structurally and
referentially separate; each app owns and loads only its own copy.

## 4. Cross-import verification (Step 2)

**Forward check** —
`grep -rn "supplier-stock-client\|quick-stock-client" desktop/nextech-mediq/ --include="*.js" --include="*.jsx" --include="*.cjs" --include="*.json" --include="*.html"`
returned 7 hits, **all comments, zero actual imports/requires**:

- `electron/security/windowDefaults.cjs:5-6` — comment contrasting security
  posture choices with quick-stock-client/supplier-stock-client.
- `src/api/client.js:2` — comment citing supplier-stock-client's client.js as
  the pattern it follows (not importing it).
- `src/services/sessionStore.js:2,14` — comments noting the session-key naming
  convention (`nexora.desktop.session`) was chosen to be compatible/consistent
  with supplier-stock-client's, not a code dependency.
- `src/services/settingsStore.js:2` — same, for `nexora.desktop.settings` key
  naming.
- `src/themes/themeLogic.js:3` — comment citing supplier-stock-client's
  `theme.js`/`theme.test.js` as design precedent.

No `import`, `require`, relative `../`-style path, or `package.json`
dependency anywhere in `nextech-mediq/` resolves into `supplier-stock-client/`
or `quick-stock-client/`. **Zero actual cross-project source imports.**

**Reverse check** — `grep -rln "nextech-mediq" desktop/supplier-stock-client desktop/quick-stock-client`
found only the two files already covered in Step 3 (`App.jsx`,
`package.json`), which reference supplier-stock-client's **own** local asset
files named `nextech-mediq-*` (Step 3) — not the `nextech-mediq/` project
directory. `quick-stock-client` has zero hits in either direction.

**Verdict: fully independent.** No code-level coupling between any of the
three apps in either direction.

## 5. Build-output / output-dir collision check (Step 4)

| App | Working dir | Vite `outDir` | Resolved vite output | electron-builder `output` | Resolved build output |
|---|---|---|---|---|---|
| supplier-stock-client | `desktop/supplier-stock-client/` | `dist` | `desktop/supplier-stock-client/dist/` | `release` | `desktop/supplier-stock-client/release/` |
| quick-stock-client | `desktop/quick-stock-client/` | (no vite step) | n/a | `release` | `desktop/quick-stock-client/release/` |
| nextech-mediq | `desktop/nextech-mediq/` | `dist` | `desktop/nextech-mediq/dist/` | `release` | `desktop/nextech-mediq/release/` |

All three use the literal relative names `dist` / `release`, but
electron-builder and Vite resolve `directories.output` / `build.outDir`
relative to **each project's own `package.json`/`vite.config.js` location**
(not a shared root). Each physically lands inside that project's own folder
tree. **No collision** — confirmed both from config inspection and from the
fact that `desktop/nextech-mediq/dist/` already exists from a prior build and
is isolated under `desktop/nextech-mediq/`.

## 6. Build/verify results for nextech-mediq (Step 5)

- `node_modules` was **already installed** — no fresh `npm install` needed or performed.
- `npm run build` (→ `vite build`) in `desktop/nextech-mediq/`: **PASS**.
  63 modules transformed, built in 981ms, emitted `dist/index.html`,
  `dist/assets/index-*.css` (6.03 kB), `dist/assets/index-*.js` (185.11 kB).
  No errors or warnings.
- `npm test` (→ `node --test tests/*.test.js tests/*.test.mjs`): **PASS**,
  22/22 tests green (API client retry/error handling, IPC channel allowlist,
  webPreferences security floor, navigation allowlist, session store
  round-trip + staleness, settings store round-trip + key namespacing, theme
  resolution). 0 failures, 0 skipped.
- Own Electron main confirmed at `desktop/nextech-mediq/electron/main/index.cjs`
  (exists). Own preload confirmed at
  `desktop/nextech-mediq/electron/preload/index.cjs` (exists, in its own
  subdirectory — structurally distinct from the flatter `electron/main.cjs`
  layout used by the other two apps).
- Did not attempt `electron-builder` packaging (`npm run dist`) — out of
  scope per the "no production deploy/publish/sign actions" constraint, and
  not requested; `vite build` + unit tests are sufficient lightweight
  verification for this task.
- Did **not** rebuild or re-verify supplier-stock-client or quick-stock-client
  (out of scope per instructions — their identity info was already gathered
  in the prior pass and nothing about them changed in this task).

## 7. Remaining risks / unresolved items

- **Duplicate `productName`**: supplier-stock-client and nextech-mediq both
  set `productName: "NexTech MediQ"` in their electron-builder config. Their
  `appId`s differ so there is no install-time technical collision, but a user
  installing both would see two Start-Menu entries with the identical display
  name. This is a naming/product decision, not a code defect — flagged, not
  fixed, since changing supplier-stock-client's branding strings is explicitly
  out of bounds for this task.
- `electron-builder --dist` packaging was not run for nextech-mediq (by
  design/scope) — so while the Vite build and unit tests pass cleanly, the
  final NSIS installer output has not been produced or inspected in this
  pass. If/when that's wanted, the config appears self-consistent and isolated
  (own appId, own output dir, own icon path) and nothing in this verification
  suggests it would fail.
- The asset-overlap situation (Section 3) is stable today because the
  filenames happen to differ in a way (`nextech-mediq-*` vs `branding/` subdir
  structure) that avoids confusion, but if supplier-stock-client's rebrand
  continues to converge on identical filenames/paths as nextech-mediq's own
  branding folder, a future contributor could conflate the two. No action
  needed now; worth a one-line note for whoever does the next rebrand phase.

## 8. Explicitly out of scope / untouched

The following modified/untracked files visible in `git status` are unrelated
feature work and were **not examined or touched** as part of this task:

- `backend/modules/legacy_order/order_process.py`, `repository.py`
- `backend/modules/procurement/decision_repository.py`,
  `workspace_repository.py`, `product_identity.py`
- `backend/modules/quick_stock/router.py`, `service.py`, `schemas.py`
- `backend/tests/test_legacy_order_warehouse_stock_sync.py`
- `frontend/src/pages/quick-stock/*` (PinGate.tsx, QuickStockPage.tsx,
  quick-stock.css, quickStockService.ts, types.ts, and the deleted
  QuickStockDetail.tsx)
- `backend/storage/whatsapp/send_log.json`

These remain exactly as they were found in the working tree; this task made
no changes to them.
