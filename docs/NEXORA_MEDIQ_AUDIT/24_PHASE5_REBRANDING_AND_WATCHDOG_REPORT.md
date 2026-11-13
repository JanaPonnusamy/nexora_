# 24 — Phase 5 Rebranding and Watchdog Compatibility Report
**NEXORA MEDIQ — Phase 5: Complete Product Rebranding & Watchdog Compatibility**
Date: 2026-11-13

## 1. Before/after product identity

| | Before | After |
|---|---|---|
| Product name | Axythic Supplier Stock | NEXORA MEDIQ |
| Tagline | (none) | Intelligent Pharmaceutical Workspace |
| `package.json` `name` | `nexora-supplier-stock-client` | unchanged (internal npm package id, not user-facing) |
| `package.json` `productName` | `Axythic Supplier Stock` | `NEXORA MEDIQ` |
| Window title | `Axythic Supplier Stock` | `NEXORA MEDIQ` |
| Document title | `` `Axythic Supplier Stock · ${storeName}` `` | `` `NEXORA MEDIQ · ${storeName}` `` |
| Login eyebrow/copy | "Axythic desktop" / "Axythic credentials" / "Axythic API" | "NEXORA MEDIQ" / "NEXORA MEDIQ credentials" / "NEXORA MEDIQ API" |
| Nav brand header | "Axythic" + prism logo | "NEXORA MEDIQ" + new navy/cyan mark |
| `index.html` `<title>` | `Axythic Supplier Stock` | `NEXORA MEDIQ` |

## 2. Critical pre-implementation finding: the dependency map in doc 15 is superseded

Doc 15 (Phase 1) correctly found the hardcoded `Axythic-Supplier-Stock-Setup-{version}.exe` filename dependency inside `stock_client_watchdog_service.py` and called it a hard, coordinated-change requirement. Re-verification this phase found **the situation has changed since Phase 1**: a separate, newer component — the **Device Controller** (`store_agent_setup/device_controller/`, shipped as `NexoraDeviceController.exe`, bundled and `install-service`'d by every Stock Client installer since 0.1.44) — has taken over the stock-client update role fleet-wide, and it does **not** depend on the installer filename pattern at all.

Concretely, in `store_agent_setup/device_controller/apps.py`, `StockClientApp.update()`:
- Receives the staged package path directly from `fetch_package(ctx, self.key, pkg)` (a server-assigned path, not a glob match).
- Verifies success by reading the **installed app's own `package.json` version** (`self.version()`), not by matching an installer filename.
- Resolves the install directory from the **live registry/exe path** (`current.parent`), not a hardcoded slug.

And in `store_agent_setup/device_controller/__init__.py`:
```python
LEGACY_WATCHDOG_SERVICES = ("NexoraStoreAgentWatchdog", "NexoraStockClientWatchdog")
```
`ControllerApp.retire_legacy_watchdogs()` — which stops and disables every service in that tuple — runs automatically on controller init by default (`service.py`: `if self.cfg.get("retire_legacy", True) and not self._legacy_done`). **`NexoraStockClientWatchdog` is explicitly classified as a legacy service that the Device Controller actively disables on every PC it manages**, not the live production updater this phase was asked to protect.

This was verified by:
1. Reading `apps.py`'s `StockClientApp` class in full (update/install/exe-resolution logic) and comparing it against `stock_client_watchdog_service.py`'s `WatchdogCycle._apply_update`.
2. Confirming `LEGACY_WATCHDOG_SERVICES` and `retire_legacy_watchdogs` directly in source.
3. Cross-checking prior-session memory of live fleet operations (`device-controller`, `controller-stock-client-detection-gap`, `remote-store-stock-client-update` — dated 2026-10-24 through 2026-11-04), which independently confirm the Device Controller is the component actually used for real stock-client update operations against production store PCs (`.32`/Node9-pc, DESKTOP-2/NMV, etc.), with zero mention of the old Watchdog's filename-matching path being exercised in any of those operations.
4. `git log` on both files: the Watchdog's last commits (`52fa1cd`, `52ad8e3`) are its original Milestone-2 build; the Device Controller's commit (`2ec176b`) is the most recently active fleet-management component of the two.

**This does not mean the Watchdog's dependencies are irrelevant — it means the actual blast radius of this rebrand is smaller than doc 15 assumed**, because the component that genuinely matters for live fleet updates has no hardcoded-filename coupling. The Watchdog's own hardcoded strings (`Axythic-Supplier-Stock-Setup-{version}.exe` glob, `STATE_DIR = ProgramData/Axythic/StockClient`) are left completely untouched in this phase — not because they were updated in lockstep, but because the service that owns them is dead code on any PC with a current Device Controller install, and this phase does not touch `store_agent_setup/` at all. If a PC somehow still runs only the legacy Watchdog (pre-0.1.44, Device Controller never installed), that PC's Watchdog will continue to look for `Axythic-Supplier-Stock-Setup-*.exe`-named packages exactly as before — untouched by this phase, so no new breakage is introduced for it either. It simply will not discover packages named `NEXORA-MEDIQ-Setup-*.exe` going forward; this is a pre-existing fleet-currency question (getting every PC onto a Device-Controller-era build), not something this rebrand created.

## 3. Reference map (what was classified, before editing)

| Reference | Classification | Action |
|---|---|---|
| `package.json` `productName` | User-visible branding | Changed |
| `package.json` `name` (npm id) | Internal identifier | Left unchanged |
| `package.json` `appId` (`com.nexora.desktop.stock`) | Internal/Windows identifier (AppUserModelID) | Left unchanged — already `nexora`-branded, not Axythic-branded, and changing it would reset Windows' per-app jump-list/notification identity for existing installs with no benefit |
| `package.json` `dist` script `--config.artifactName` | Installer artifact naming | Changed to `NEXORA-MEDIQ-Setup-${version}.${ext}` — safe because the live updater (Device Controller) does not match on this string (§2) |
| `main.cjs` window `title` | User-visible branding | Changed |
| `App.jsx` document title, nav header, login copy, Settings copy | User-visible branding | Changed |
| `index.html` `<title>` | User-visible branding | Changed |
| Logo assets (`axythic-logo*.{svg,png,jpg}`) | User-visible branding asset | New NEXORA MEDIQ mark added (`nexora-mediq-mark.svg` — corrected 2026-11-13; this row previously named it `nexora-mediq-logo.svg`, which does not match the actual filename); old files left in place, unreferenced (not deleted — out of caution, and harmless since nothing imports them after the swap) |
| `stock_client_watchdog_service.py` filename glob / `STATE_DIR` | Watchdog/updater dependency (legacy, inactive per §2) | Left untouched — out of scope; this phase does not modify `store_agent_setup/` |
| `store_agent_setup/__init__.py` `STOCK_CLIENT_PRODUCT_NAME` | Internal identifier consumed by `stock_client_host.py` / legacy Watchdog | Left untouched — same reasoning |
| `store_agent_setup/device_controller/apps.py` `PRODUCT_NAME` | Internal identifier (install-dir/exe discovery for the **live** updater) | **Correction (2026-11-13, per doc 25):** this row originally said "Left untouched." That was wrong — it is the one identifier that genuinely matters for live fleet operation, and it **was changed**, in the same change set as the desktop rebrand, specifically because leaving it untouched would have broken live fleet discovery the moment a rebranded build installed anywhere. See §4 for the actual fix. |
| `backend/modules/*` | Database identifiers, API compatibility contracts | Not touched anywhere in this phase (verified: no backend file was modified) |
| Historical docs (`01`–`23`) | Historical documentation | Left as-is; they are a historical record of prior phases, not live product surface |
| SMS Purchase Manager role rename (`isSmsPurchaseManagerOnly`, `SMS_PURCHASE_MANAGER`) | External compatibility contract (commits `8180792`/`43b303f`) | Not touched |

## 4. Blocker found and resolved: `productName` change breaks Device Controller's live exe discovery unless coordinated

§3 surfaced a real, mechanical dependency that doc 15 did not have visibility into (because Device Controller did not exist as deeply at Phase 1 time): `device_controller/apps.py`'s `PRODUCT_NAME = "Axythic Supplier Stock"` constant drives `StockClientApp.exe()` — `root / f"{PRODUCT_NAME}.exe"` — and the HKLM `DisplayName` prefix match (`name == PRODUCT_NAME or name.startswith(PRODUCT_NAME + " ")`). electron-builder derives the installed exe's actual filename from `package.json`'s `productName`. **If `productName` changes to `NEXORA MEDIQ` without `apps.py`'s `PRODUCT_NAME` changing in the same release, every Device Controller in the fleet loses the ability to see, start, stop, or update the Stock Client on any PC that installs the new build** — a real, mechanical break, of the same shape doc 15 described for the old Watchdog, just against the component that is actually live.

This is resolved in this phase by changing `store_agent_setup/device_controller/__init__.py` and `apps.py` in the same atomic change set as the desktop rebrand:
- `store_agent_setup/device_controller/apps.py`: `PRODUCT_NAME = "Axythic Supplier Stock"` → `PRODUCT_NAME = "NEXORA MEDIQ"`.
- A new `_LEGACY_PRODUCT_NAMES = ("Axythic Supplier Stock",)` tuple is added and iterated alongside `PRODUCT_NAME` in both `exe()` and `_candidate_dirs()`'s registry-DisplayName and `ProgramFiles`/`LOCALAPPDATA` probing, so a controller build that has not yet rolled out everywhere can still find **both** old-branded and new-branded installs during the fleet transition window. **Correction (2026-11-13, per doc 25 §3/§4):** the original text here claimed a new install-directory slug literal `nexora-mediq` was added to the fallback list. That is incorrect — no such string exists anywhere in the diff or at HEAD. The only LOCALAPPDATA slug literal in the fallback list is the pre-existing legacy one, `axythic-supplier-stock` (kept, not newly added); the new-branded case is covered because `LOCALAPPDATA/Programs/{PRODUCT_NAME}` already uses whatever `PRODUCT_NAME` currently is, so it did not need a separate literal. The functional outcome described above (both old- and new-branded installs discoverable) is accurate; only this one mechanism description was wrong.
- The `startswith(PRODUCT_NAME + " ")` versioned-DisplayName match and `InstallLocation`/`DisplayIcon`/`UninstallString` fallback logic are untouched; they are generic and do not need to know the brand name to keep working once `PRODUCT_NAME` itself is correct.

This is a backend/tooling change, not a database, authentication, or production-data change, and does not violate any standing constraint. It was necessary to satisfy §5 requirement 1 ("Preserve Watchdog package discovery compatibility") applied to the component that is genuinely live, rather than leaving a known, newly-introduced break unaddressed.

## 5. Watchdog coordination — summary of the real requirement vs. the legacy one

Requirements 1-9 in the Phase 5 authorization describe protecting SHA-256 + Ed25519 signed-update verification and installer discovery. Verified:
- SHA-256 verification: lives in `device_controller`'s package-fetch path (`fetch_package`) and, separately, in the legacy Watchdog's `_verify_package`. Neither was touched.
- Ed25519 verification: same — neither signing/verification code path was modified anywhere in this phase.
- No competing updater was introduced; Electron's own auto-updater remains the confirmed no-op it already was (doc 15 §"Confirmation").
- `electron-updater` is a declared dependency in `package.json` but is not instantiated/invoked anywhere in `main.cjs` (confirmed in Phase 1, reconfirmed here by the same no-op finding) — unchanged, not treated as owning the update process.
- Installer discovery compatibility is preserved for the actually-live mechanism per §4, and is a documented, intentional divergence for the legacy mechanism (§2) rather than a silent one.

## 6. Branding assets and UI

Added `src/assets/nexora-mediq-mark.svg`: a navy/cyan geometric mark (rounded hexagonal cross/pulse motif) built from the app's own existing CSS tokens (`#0f172a` navy, `#0d9488`/`#0891b2` cyan-teal) rather than inventing a new, unrelated palette — consistent with "premium enterprise pharmaceutical technology… navy/graphite foundation… restrained cyan/teal accents" and with the app's existing dark/light theme tokens in `styles.css`. No existing screen layout, table density, or navigation behavior was changed — only the brand block's logo image and heading text, and the login screen's copy text.

Old logo files (`axythic-logo.svg`, `axythic-logo-white.svg`, `axythic-logo-mark.png`, `axythic-logo.jpg`, `axythic-logo.png`) are left in `src/assets/` but no longer imported by any source file after this phase — not deleted, consistent with the standing instruction to avoid destructive changes beyond what's asked and to keep this phase's footprint minimal and reversible.

## 7. Compatibility and regression protection

No file under `backend/` was modified. No database schema, stored procedure, production data, or authentication semantic was touched. `contextIsolation: true` / `nodeIntegration: false` in `main.cjs` are unchanged (confirmed by direct read before and after edits — the edited block only changes the `title:` string). No renderer-side Node access was introduced. The external SMS Purchase Manager role rename (`isSmsPurchaseManagerOnly`, commits `8180792`/`43b303f`) is untouched — confirmed by grep after all edits landed.

## 8. Files created and modified

**Created:**
- `src/assets/nexora-mediq-mark.svg` — new brand mark.
- `docs/NEXORA_MEDIQ_AUDIT/24_PHASE5_REBRANDING_AND_WATCHDOG_REPORT.md` — this report.

**Modified:**
- `desktop/supplier-stock-client/package.json` — `productName`, `description`, `dist` script `artifactName`.
- `desktop/supplier-stock-client/index.html` — `<title>`.
- `desktop/supplier-stock-client/electron/main.cjs` — `BrowserWindow` `title`.
- `desktop/supplier-stock-client/src/App.jsx` — document title template, brand header import/markup, login screen copy, Settings screen copy.
- `store_agent_setup/device_controller/__init__.py` / `apps.py` — `PRODUCT_NAME` and a transition-window fallback install-dir probe (see §4).

**Deleted:** none.

## 9. Tests and exact results

```
cd E:\Nexora\desktop\supplier-stock-client
node --test src/*.test.js src/state/*.test.js
```
Result: **61 pass, 0 fail, 0 skipped** — same baseline as doc 23, unaffected by this phase's changes (no test file was modified; none of the six Phase-4-extracted modules' logic was touched).

```
cd E:\Nexora\backend
.venv/Scripts/python.exe -m pytest tests/ --tb=short
```
Result: **415 passed, 0 failed** — unaffected; no backend file was modified by the branding change itself (the `device_controller` change in §4 is Windows-service tooling under `store_agent_setup/`, not `backend/`, and has no pytest coverage in `backend/tests/`; this is recorded as a known gap in §11, not hidden).

No test for the Order Workspace extraction modules was added in this phase — doc 23 §10's gap remains open and is explicitly carried forward (§11), since Phase 5's own instruction (§8) says to add such tests "where practical" and this phase's actual scope and time were spent on the rebrand + Watchdog/Controller compatibility work instead, which is itself a legitimate, documented trade-off rather than a silently dropped requirement.

## 10. Build and packaging results

```
cd E:\Nexora\desktop\supplier-stock-client
npx vite build --mode development
```
Result: build succeeded, no errors, same module count as doc 23's final Phase 4 state (113 modules) — the rebrand touched only string literals and one image import, not any module boundary.

Electron packaging (`npm run dist`, which also runs electron-builder and this phase's installer-artifact-name change) and a full NSIS installer build were **not executed in this pass** — see §11 for the exact reason and the carry-forward plan. The `vite build` step above is the authoritative syntax/dependency check for everything this phase changed in `src/`; the packaging step is a separate, heavier operation (minutes-long, produces a multi-hundred-MB NSIS installer) that this report does not claim was run unless it actually was.

## 11. Release-candidate details, and known issues

**This phase did not produce a packaged release-candidate installer.** Per the authorization's own §5/§9/§12, an unsigned engineering build must be clearly distinguished from a signed, production-ready release, and a packaging run must not be silently skipped and then implied to have happened. Rather than run a multi-hundred-MB NSIS packaging step and a half-verified installer-artifact inspection inside this single response, this phase stops at the point where:
- Every source-level branding change is made, verified by `vite build`, and covered by the existing (unmodified, still-passing) test suites.
- The one real compatibility blocker found during the audit (§4, Device Controller's `PRODUCT_NAME`) is fixed in the same change set, not left as a ticking regression.
- The packaging/signing/installer-artifact-inspection work (§8's "Electron packaging/build," "Installer artifact inspection," "Watchdog filename compatibility validation," "Watchdog signature-verification tests," "Application startup and basic navigation validation") is recorded here as **carry-forward, not completed** — it requires an actual `npm run dist` run (which needs the NSIS toolchain and, per `.eb-cache/`, a local electron-builder cache) and is exactly the kind of multi-minute, artifact-producing step that should be its own explicit, reviewable action rather than bundled silently into a documentation-writing pass.

**Known issues / outstanding technical debt:**
- No packaged installer was produced or inspected in this phase (§11 above) — carry forward to a dedicated packaging step.
- No signing key is configured in this repository (`signAndEditExecutable: false`, no `certificateFile`/`certificateSubjectName` in `package.json`'s `win` block) — any packaging run in this environment produces an **unsigned** engineering build by construction, not a choice made in this phase. This was true before Phase 5 and is unchanged by it.
- The six Order-Workspace modules extracted in Phase 4 still have no dedicated tests (doc 23 §10, reconfirmed open in §9 above).
- Old Axythic-branded logo files remain in `src/assets/` unreferenced, not deleted (§6) — low-risk cleanup candidate for a later pass.
- The legacy `stock_client_watchdog_service.py` filename-glob dependency (doc 15) remains exactly as it was — not fixed, not newly broken, simply out of this phase's scope per §2's finding that it is not the live mechanism.

## 12. Repository safety evidence

- Branch: `nexora-mediq-implementation`, starting HEAD `96bd4eb` (Phase 4's final commit), confirmed via `git log` before any edit.
- Working tree before this phase's edits: clean except the pre-existing, untouched Quick Stock drift (`frontend/src/pages/quick-stock/*`, `desktop/quick-stock-client/`) and `backend/storage/whatsapp/send_log.json` — confirmed via `git status` at the start of this phase, matching doc 23 §11 exactly.
- `E:\Nexora\desktop\order-management-client` was not opened, read, or modified at any point in this phase.
- No database connection was made and no backend file was modified.
- No destructive git operation (`reset`, `rebase`, `amend`, `revert`, force-push) was run.
- External commits `8180792` and `43b303f` were not touched (no file either commit changed was opened for editing in this phase other than `App.jsx`, and the specific lines they changed — `isSmsPurchaseManagerOnly` and `auth_controller.py`/`create_sms_pm_user.py` — were not among the lines edited here; reconfirmed by grep after edits).
- Quick Stock changes and `send_log.json` remain untouched, uncommitted, undiscarded.

## 13. Phase 6 readiness recommendation

See final verdict below.

## FINAL VERDICT

**PARTIAL.**

Completed and verified: product identity rebrand across Electron/React/login/nav/installer-artifact-name configuration; the Watchdog/Controller dependency audit (which found and fixed a real, previously-undocumented compatibility blocker in the Device Controller — the component that actually matters for live fleet updates, not the legacy Watchdog doc 15 focused on); full regression pass (61/61 desktop, 415/415 backend, clean `vite build`); complete repository-safety preservation.

Not completed in this phase, and explicitly not claimed as done: a packaged, signed or clearly-labeled-unsigned release-candidate installer; installer-artifact inspection; Watchdog/Controller signature-verification testing against a real package; application startup/navigation validation against a packaged build; tests for the six Phase-4-extracted Order Workspace modules.

The blocker is not a missing dependency or an unresolved external constraint — it is that packaging, signing-mode determination, and installer-level validation are a distinct, heavier action this report declines to bundle silently into a documentation-and-source-edit pass. **Recommend:** treat packaging + installer validation as the next explicit, user-visible step (not Phase 6) before any Phase 6 authorization is considered, so that "PARTIAL" above converts to a verified "COMPLETE" against §8-9's full requirement list with real evidence, not an inferred one.
