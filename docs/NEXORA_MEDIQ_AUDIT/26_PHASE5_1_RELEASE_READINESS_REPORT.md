# 26 — Phase 5.1 Release Readiness Report
**NEXORA MEDIQ — Release Readiness & Device Controller Hardening**
Date: 2026-11-13

## 1. Executive summary

Phase 5.1 closed the specific engineering gaps doc 25's independent audit flagged: it corrected doc 24's two inaccurate passages, re-verified the frontend build live, built a full automated test suite for `StockClientApp` (previously zero coverage), resolved the dual-install-ambiguity question with regression tests rather than narrative, classified the Watchdog's operational status from direct evidence rather than inference, and re-ran the full regression suite. One genuine, pre-existing production-code defect was found and fixed in the course of writing tests (`StockClientApp` had no `is_running()` method, so `update()` would have raised `AttributeError` on its very first real invocation — introduced in the Device Controller's original commit, unrelated to the rebrand). No packaging, signing, or installer work was performed, per this phase's explicit authorization boundary.

**Verdict: PARTIAL.** Every authorized engineering/validation task in this phase passed. It remains PARTIAL rather than COMPLETE only because Phase 5's own unresolved items — a packaged installer, a signed or clearly-labeled-unsigned release candidate, and installer-level Watchdog/Controller validation — are out of this phase's authorized scope entirely, not because anything attempted here failed.

## 2. Starting Git baseline

- Branch: `nexora-mediq-implementation`.
- Starting HEAD: `8092139` (doc 25, the independent audit).
- `960b3a5`, `ef4192c`, `b3b809a`, `8092139` all confirmed ancestors of HEAD via `git merge-base --is-ancestor` before any edit.
- Phase 2-4 commit chain confirmed intact (unbroken ancestry back through `96bd4eb`).
- External commits `8180792`/`43b303f` confirmed intact.
- `backend/storage/whatsapp/send_log.json`: modified-in-place, uncommitted, untouched by this phase (confirmed before and after).
- Concurrent, unrelated, uncommitted Quick Stock drift was present and evolving at the start of this phase (`backend/modules/quick_stock/router.py`, `service.py`, five `frontend/src/pages/quick-stock/*` files modified, `QuickStockDetail.tsx` deleted, `QuickStockAllStoresDetail.tsx`/`QuickStockLinks.tsx`/`quickStockUrls.ts` untracked, plus an untracked `desktop/quick-stock-client/` directory) — this is a different, concurrent session's in-progress work on a pre-existing out-of-scope feature (first flagged in Phase 2), not anything this phase or any Phase 5 commit touched. Confirmed untouched at the end of this phase by diffing the final `git status` against this baseline and staging only this phase's own three files.

## 3. Report 24 corrections

Two inaccuracies found and corrected in `24_PHASE5_REBRANDING_AND_WATCHDOG_REPORT.md`, both flagged by doc 25:

1. **§4**: previously claimed a new install-directory slug literal `nexora-mediq` was added to the fallback probe list. No such string exists anywhere in the `ef4192c` diff or at HEAD. Corrected in place to describe the actual mechanism: the `_LEGACY_PRODUCT_NAMES` tuple, iterated alongside `PRODUCT_NAME`, with the pre-existing `axythic-supplier-stock` literal kept (not newly added) as the one LOCALAPPDATA slug fallback that needs its own literal (the new-branded case needs no new literal, since it already uses whichever string `PRODUCT_NAME` currently holds).
2. **§3 reference-map table**: the row for `apps.py`'s `PRODUCT_NAME` said "Left untouched" — directly contradicted by §4 of the same document, which describes changing exactly that identifier. Corrected to state plainly that this was the one identifier that genuinely mattered and that it was, in fact, changed.

Both corrections are inline edits with an explicit "Correction (2026-11-13, per doc 25)" marker, preserving the original audit trail rather than silently rewriting history — per this phase's instruction to document the correction, not erase it. No other unsupported claim was found on a full re-read of the rest of doc 24.

## 4. Frontend build results

```
cd E:\Nexora\desktop\supplier-stock-client
npx vite build --mode development
```
Executed live, this phase, against current HEAD (prior to this phase's own commit, and re-confirmed passing after it — this phase's changes are backend/Python-only and cannot affect this build).

- **Exit code: 0.**
- 113 modules transformed.
- Build time: 567ms (reported by Vite); wall-clock including `npx`/Vite startup overhead: ~4.96s.
- Output: `desktop/supplier-stock-client/dist/` (`index.html` 1.06kB, `assets/index-*.css` 299.11kB, `assets/xlsx.min-*.js` 862.97kB, `assets/index-*.js` 985.76kB).
- Warning: the same pre-existing chunk-size-over-500kB warning present since before Phase 4 — unrelated to any Phase 5/5.1 change, not a new regression.
- This confirms, independently and for the first time this phase (doc 25 had explicitly left this UNVERIFIED), that report 24's original build claim was accurate.

This build result proves the Electron/React source compiles and bundles correctly. It does **not** prove Electron packaging, NSIS installer generation, or Watchdog/Controller runtime compatibility — none of which this phase attempted or claims.

## 5. Device Controller test architecture

New file: `store_agent_setup/device_controller/test_apps_stock_client.py` (22 tests, pytest, run via `backend/.venv`'s Python 3.12 interpreter since `store_agent_setup` has no dedicated venv of its own and no test previously existed there).

Design:
- **Filesystem-based cases** use real `tmp_path` directories standing in for `ProgramFiles`/`LOCALAPPDATA`, with `os.environ["ProgramFiles"]` and `host.user_localappdata` monkeypatched per test — never the real local paths.
- **Registry-based cases** use a hand-built fake `winreg` module (`_patch_winreg` helper) injected via `monkeypatch.setitem(sys.modules, "winreg", ...)`, simulating `OpenKey`/`QueryInfoKey`/`EnumKey`/`QueryValueEx` against an in-memory list of fake subkeys — the real Windows registry is never opened by any test that uses it.
- **A critical isolation fix mid-phase**: the first run of this suite (before the `autouse` fixture existed) discovered that **this development machine has a real, locally-installed "Axythic Supplier Stock 0.1.71"** registered in `HKLM\...\Uninstall` (confirmed via a read-only `Get-ItemProperty` PowerShell query, from earlier `npm run dist`/install cycles during this project's own work — not a production fleet machine) — any test that did not explicitly fake the registry was reading this real, local entry and producing machine-dependent, non-deterministic results. Fixed by adding an `autouse=True` fixture (`_never_touch_real_registry`) that installs an empty fake registry by default for every test in the file; the registry-specific tests override it with their own fake subkeys. This also confirmed, independently and incidentally, that `NexoraDeviceController` is genuinely `RUNNING` as a service on this machine (`sc query`) while `NexoraStockClientWatchdog` is **not installed at all** (`sc query` → error 1060) — direct evidence folded into §9 below.

## 6. Exact test cases and results

All 14 authorization-required scenarios are covered, several by more than one test:

| # | Scenario | Test(s) |
|---|---|---|
| 1 | New NEXORA MEDIQ install discovered | `test_discovers_new_product_name_install_in_programfiles`, `..._in_localappdata` |
| 2 | Legacy Axythic install discovered | `test_discovers_legacy_product_name_install`, `test_discovers_legacy_slug_install_in_localappdata` |
| 3 | Registry DisplayName matches new name | `test_registry_displayname_matches_new_product_name` |
| 4 | Registry DisplayName matches legacy name | `test_registry_displayname_matches_legacy_product_name` |
| 5 | Install dir discovered through supported paths | `test_all_supported_candidate_paths_are_discoverable` (×3, parametrized) |
| 6 | Executable missing | `test_exe_missing_returns_none` |
| 7 | Registry entry missing | `test_no_registry_entries_falls_back_to_filesystem_guesses` |
| 8 | Invalid installation directory | `test_invalid_install_location_is_skipped_safely` |
| 9 | Multiple candidate directories | `test_multiple_candidate_directories_real_one_is_found` |
| 10 | Old and new installs coexisting | `test_dual_install_programfiles_new_name_preferred_over_localappdata_legacy`, `..._same_directory_...`, `..._localappdata_...` |
| 11 | Correct exe selected for update | `test_update_targets_the_discovered_install_directory` |
| 12 | Incorrect/unrelated exe rejected | `test_unrelated_exe_with_similar_name_not_matched`, `test_registry_entry_for_unrelated_app_is_ignored` |
| 13 | No installation found | `test_no_installation_found_anywhere` |
| 14 | Malformed registry info handled safely | `test_malformed_registry_display_name_missing_handled_safely`, `..._install_location_empty_falls_through` |

Command and result:
```
cd E:\Nexora
backend/.venv/Scripts/python.exe -m pytest store_agent_setup/device_controller/test_apps_stock_client.py -v -p no:cacheprovider
```
**22 passed, 0 failed, 0 skipped**, 0.24-0.66s across repeated runs, run against current HEAD both before and after this phase's own commit.

## 7. Dual-install ambiguity analysis

Resolved by direct source reading plus regression test, not assumption:

`_candidate_dirs()` returns directories in a fixed order: registry-matched directories first (in registry enumeration order), then every `ProgramFiles`-family path (`ProgramFiles/{name}`, `ProgramFiles/Nexora Supplier Stock/{name}`) for `PRODUCT_NAME` then each legacy name in turn, then every `LOCALAPPDATA/Programs/{name}` path in the same name order, then finally the hardcoded legacy LOCALAPPDATA slug `axythic-supplier-stock`. `exe()` then walks that directory list in order and, **within each directory**, checks `PRODUCT_NAME` before any legacy name.

This gives two deterministic guarantees, proven by `test_dual_install_*`:
1. **Within any single directory**, the current product name always wins over a legacy one.
2. **Across different directories**, directory-family order wins regardless of name: a legacy-named install in a ProgramFiles-family path is found before a new-named install in a LOCALAPPDATA-family path, because ProgramFiles-family entries are enumerated first.

This is **not** "newest version wins" and **not** "current PRODUCT_NAME always wins globally" — it is directory-family precedence with name precedence only as a tiebreaker inside one directory. This is now stated as fact (backed by three passing tests), not guessed. No code change was made to alter this ordering — the authorization's "design a deterministic selection strategy... or document the ambiguity instead of guessing" is satisfied by documenting the strategy that already exists and proving it holds, since changing `_candidate_dirs()`'s directory ordering was judged out of scope for a "dual-install edge case" explicitly described as low-probability (normal `perMachine` NSIS installs reinstall in place, they do not create a second parallel install) and not something doc 25 asked to be fixed, only investigated.

## 8. Device Controller risk assessment

- **Fixed in this phase**: `StockClientApp` had no `is_running()` method; `update()` called `self.is_running()` unconditionally whenever `current` (the discovered exe) was truthy. This is a genuine, pre-existing defect (introduced in commit `2ec176b`, the Device Controller's original build, unrelated to Phase 5's rebrand) that would raise `AttributeError` on the first real `update()` call against any installed Stock Client. Fixed by adding `is_running()` alongside the existing `status()` method, both backed by the same `host.is_running(exe)` check — a minimal, narrowly-scoped correction of a proven defect, consistent with this phase's explicit authorization to do so.
- **Start/stop/update/status all route through the same `exe()` call** — confirmed by re-reading the file after this phase's edit; no second, un-synchronized hardcoded product-name copy exists anywhere in `apps.py`.
- **Still no coverage for anything outside `StockClientApp`** (other `App` subclasses in the same file remain untested) — out of this phase's scope, not claimed as addressed.
- **Residual risk, documented not fixed**: the cross-directory dual-install ordering (§7) could, in a genuinely abnormal machine state (two parallel installs via different mechanisms), select an older install over a newer one. Judged acceptable to leave as documented behavior rather than redesign, per the authorization's own permission to document rather than guess at a fix.

## 9. Watchdog operational status and supporting evidence

**Classification: RETIRED.**

Evidence (source-level and local-machine-only; no fleet machine was contacted):

1. **The NSIS installer itself no longer installs the Watchdog.** `desktop/supplier-stock-client/build/installer.nsh`'s `customInstall` macro — the actual code that runs on every real install/update — only ever invokes `NexoraDeviceController.exe install-service`. It contains no reference to the Watchdog at all.
2. **`LEGACY_WATCHDOG_SERVICES` explicitly names it** (`store_agent_setup/device_controller/__init__.py`: `("NexoraStoreAgentWatchdog", "NexoraStockClientWatchdog")`), and `ControllerApp.retire_legacy_watchdogs()` stops and disables every service in that tuple, running automatically on controller init by default (`service.py`: `if self.cfg.get("retire_legacy", True) and not self._legacy_done`) — confirmed again, directly, this phase.
3. **Direct, local, read-only evidence from this development machine** (not a production fleet PC, but a machine that has gone through multiple real `npm run dist`/install cycles during this project's own work): `sc query NexoraStockClientWatchdog` → *"The specified service does not exist as an installed service"* (error 1060). `sc query NexoraDeviceController` → **RUNNING**. This is the single strongest piece of evidence gathered this phase: a machine with a real, currently-installed Stock Client (confirmed via the real registry entry found in §5) has no Watchdog service at all, only a running Device Controller.
4. **`git log` confirms the Watchdog's source has not been touched since its original build commit** (`52fa1cd`/`52ad8e3`, Milestone 2) except by an unrelated dependency-vendoring commit (`2795af9`, "add virtual environment site-packages") — no feature work, no bugfix, no maintenance commit of any kind in its history since.
5. **`main.cjs`'s own comment is stale**, still describing the Watchdog as the owning update mechanism (written before the Device Controller existed) — this is acknowledged explicitly as a documentation artifact, not evidence that the Watchdog is active; `initAutoUpdates()` itself remains a no-op regardless of which mechanism the comment describes.

**Limitation, stated per this phase's instruction not to infer RETIRED from missing local references alone:** this classification does not rest on absence alone. It rests on the installer's own code no longer invoking it (point 1), an active, in-source disablement mechanism that names it by service name (point 2), and direct, positive, local evidence of exactly that disablement having occurred on a real installed machine (point 3). This audit cannot observe every machine in the live production fleet directly — that would require contacting fleet machines, explicitly out of bounds — so "RETIRED fleet-wide, with zero exceptions on every PC regardless of install age" remains formally unverifiable from inside this repository. What is verified is that the retirement mechanism exists, runs by default, and has been directly observed to take effect on at least one real machine with a real prior install.

**Per the authorization's RETIRED branch**: Watchdog source is not modified, deleted, or disabled in this phase. The filename incompatibility (`NEXORA-MEDIQ-Setup-*` vs. the Watchdog's hardcoded `Axythic-Supplier-Stock-Setup-*` glob) remains exactly as doc 24/25 described it — a real, unaddressed divergence for a component with strong evidence of being inactive, not a live release blocker.

## 10. Installer filename compatibility status

Unchanged from doc 24/25: the Watchdog's glob does not and will not match `NEXORA-MEDIQ-Setup-*` artifacts. Given §9's RETIRED classification, this is **not treated as a release blocker** for the live update path (Device Controller, confirmed immune to filename coupling in doc 24 §2 and unaffected by anything in this phase). It remains a documented, permanent incompatibility for the legacy mechanism specifically, carried forward as a historical note rather than an open risk.

## 11. Frontend regression results

```
cd E:\Nexora\desktop\supplier-stock-client
node --test src/*.test.js src/state/*.test.js
```
Re-run live, this phase, against current HEAD (after this phase's own commit — desktop code is unaffected by this phase's backend-only changes, confirmed by re-running rather than assumed).

**61 pass, 0 fail, 0 skipped, 0 cancelled, 0 todo.** Duration ~2.07s. Same baseline as every prior phase report; not assumed, independently re-run.

## 12. Backend regression results

```
cd E:\Nexora\backend
.venv/Scripts/python.exe -m pytest tests/ --tb=short -q
```
Re-run live, this phase, against current HEAD.

**415 passed, 0 failed, 21 warnings** (same pre-existing FastAPI `on_event` deprecation warnings documented since doc 19 — unrelated to this phase). Duration ~10.9s.

Device Controller tests (§6) are a separate suite, outside `backend/tests/`, run and reported independently: **22 passed, 0 failed.**

No test failed at any point in this phase. No assertion was weakened or removed. No pre-existing failure needed to be triaged, because there was none.

## 13. Files created and modified

**Created:**
- `store_agent_setup/device_controller/test_apps_stock_client.py` — 22 tests.
- `docs/NEXORA_MEDIQ_AUDIT/26_PHASE5_1_RELEASE_READINESS_REPORT.md` — this report.

**Modified:**
- `docs/NEXORA_MEDIQ_AUDIT/24_PHASE5_REBRANDING_AND_WATCHDOG_REPORT.md` — two corrections (§3 above).
- `store_agent_setup/device_controller/apps.py` — added `StockClientApp.is_running()` (defect fix, §8).

**Deleted:** none.

**Not touched by this phase:** any file under `backend/modules/quick_stock/`, `frontend/src/pages/quick-stock/`, `backend/storage/whatsapp/send_log.json`, `desktop/quick-stock-client/`, `E:\Nexora\desktop\order-management-client`, any backend file outside the test-run itself, any Electron/React source file, any signing key or certificate, any NSIS/electron-builder configuration.

## 14. Unresolved issues

- No packaged installer exists for the `NEXORA MEDIQ` identity (unchanged from doc 24/25; out of this phase's scope by design).
- No signing key is configured in this repository (unchanged, pre-existing, not a Phase 5/5.1 condition).
- The six Phase-4-extracted Order Workspace modules still have no dedicated tests (doc 23 §10 gap, not in this phase's authorized scope).
- Other `App` subclasses in `apps.py` (`StoreAgentApp`, `HoBackendApp`, `ControllerApp`, etc.) remain untested — only `StockClientApp` was in scope this phase.
- The cross-directory dual-install ordering (§7) is documented, proven, and judged acceptable, but not hardened against the specific abnormal-coexistence case; left as-is per the authorization's own "document the ambiguity instead of guessing" allowance.
- RETIRED classification for the Watchdog (§9) is evidence-based but formally bounded to what this repository and this one local machine can show — not a claim about every machine in the live fleet.

## 15. Production safety confirmation

- No production database was connected to, queried, or modified.
- No production fleet machine was contacted, and no Device Controller start/stop/update/publish action was invoked against any real installation (the one `sc query` command run against this development machine is a local, read-only service-status query, not a fleet operation).
- No signing key was generated, modified, or exposed.
- No update feed was published to.
- No installer was built, packaged, or distributed.
- SHA-256 and Ed25519 verification code paths (Watchdog's `_verify_package`, and the signing-dependent parts of the fleet-update pipeline generally) were not opened for editing anywhere in this phase.
- `backend/storage/whatsapp/send_log.json` and the Quick Stock drift remain exactly as they were at the start of this phase — confirmed via `git status` before and after, and via the specific `git add` of only this phase's three intended files before committing.
- `E:\Nexora\desktop\order-management-client` was not opened, read, or referenced anywhere in this phase.
- No destructive git operation (`reset`, `rebase`, `amend`, `revert`, `cherry-pick`, force-push) was performed. One ordinary, additive commit (`386f313`) was created on top of `8092139`.

## 16. Phase 5 completion recommendation

Phase 5 (the rebrand itself) remains correctly classified **PARTIAL**, as doc 24 and doc 25 both concluded, for the same reason both gave: the source-level rebrand and its one real compatibility fix are done and verified, but packaging/signing/installer-level validation never happened and was never claimed to have happened. Phase 5.1 does not change that classification for Phase 5 itself — it was never in scope to do so, since packaging/signing/installer work was explicitly excluded from this phase's own authorization too.

## 17. Packaging/signing authorization requirements

Before a packaged, installer-level release candidate can exist, a **separate, explicit authorization** is needed covering, at minimum:
1. Running `npm run dist` (electron-builder + NSIS) to actually produce a `NEXORA-MEDIQ-Setup-*.exe` artifact.
2. A decision on signing: either explicit acknowledgment that the resulting artifact is an unsigned engineering build (no certificate is configured in this repository today), or supplying/configuring real signing credentials — the latter is a decision with its own security weight and should not be bundled into a routine build-authorization request.
3. Installer-artifact inspection once a real artifact exists: confirming the NSIS package installs cleanly, the Device Controller's `install-service` step runs as expected, and the installed app registers under the `NEXORA MEDIQ` identity this phase's tests already proved `apps.py` can discover.
4. Explicit confirmation that no such packaging run publishes to the live update feed, deploys to any store, or is distributed to any production machine — consistent with every prior phase's boundary.

## 18. Recommended next phase

Not Phase 6. Per this phase's own instruction, Phase 6 is not started. The natural next step, if and when authorized, is the packaging/signing/installer-validation pass described in §17 — scoped as its own explicit, reviewable action, not folded silently into a future phase's broader mandate. Until that happens, "Phase 5 complete and release-ready" remains an inaccurate characterization regardless of how clean the source-level work is.

## FINAL VERDICT

**PARTIAL.**

All authorized Phase 5.1 engineering and validation tasks passed: doc 24 corrected, frontend build independently re-verified, a complete Device Controller test suite built and passing (22/22, covering all 14 required scenarios plus the dual-install question), a real pre-existing production-code defect found and fixed, the Watchdog's operational status classified as RETIRED on solid (if necessarily local) evidence rather than inferred from silence, and the full existing regression suite re-run and passing (61/61 desktop, 415/415 backend). It remains PARTIAL, not COMPLETE, only because packaging, signing, and installer-level validation are outside this phase's authorized scope entirely — not because anything this phase attempted failed or was left half-done.
