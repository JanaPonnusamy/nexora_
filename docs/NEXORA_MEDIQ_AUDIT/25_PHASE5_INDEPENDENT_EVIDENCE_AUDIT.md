# 25 — Phase 5 Independent Evidence Audit
**NEXORA MEDIQ — Independent, read-only verification of commits `960b3a5`, `ef4192c`, `b3b809a` and of report 24**
Date: 2026-11-13
Auditor stance: skeptical. No claim below is accepted because it was *written*; each is checked against the diff, the source at HEAD, or a command run during this audit.

## 1. Executive verdict

**PARTIAL**, same overall classification report 24 gave itself, but reached independently and for a narrower set of reasons. The desktop rebrand (`960b3a5`) and the Device Controller compatibility fix (`ef4192c`) are real, narrow, verifiably-passing changes — not fabricated or oversold on the points that matter most (test counts, security flags, no packaging claimed). One concrete inaccuracy was found in report 24's own text (§4's "`nexora-mediq` slug" claim does not match the actual diff — see §4 below). No evidence exists, because none was produced, for packaging, signing, installer-artifact inspection, or Device-Controller runtime behavior against a live install. Those remain exactly what report 24 calls them: not done, not claimed as done.

## 2. Git integrity (Part A)

Verified directly, this session:

| Check | Result |
|---|---|
| Current branch | `nexora-mediq-implementation` |
| HEAD | `b3b809aadb3534fc457ff04c0f7126415e76472f` |
| `960b3a5`, `ef4192c`, `b3b809a` are ancestors of HEAD | YES (`git merge-base --is-ancestor`, all three) |
| Author/committer | All three: Jana Ponnusamy `janaponnusamy@gmail.com`, both author and committer (no identity substitution) |
| Timestamps | `960b3a5` 09:29:47, `ef4192c` 09:30:03, `b3b809a` 09:30:08 (2026-11-13 +0530) — strictly sequential, 16s apart then 5s apart |
| Parents | `960b3a5`→`96bd4eb` (Phase 4's final commit), `ef4192c`→`960b3a5`, `b3b809a`→`ef4192c` — a clean linear chain, no merge, no rewritten history |
| `8180792` / `43b303f` still ancestors of HEAD | YES |
| Phase 2-4 commits intact | YES — full chain from `96bd4eb` back through the Phase 4 extraction commits is unbroken |
| Working tree | Not clean, but the only drift beyond Phase 5 is **new, unrelated, uncommitted Quick Stock edits** (`backend/modules/quick_stock/router.py`, `service.py`, `frontend/.../types.ts` — a `/stores` endpoint added, timestamped ~09:33-09:36, i.e. *after* all three Phase 5 commits). This is someone else's concurrent in-progress work on the pre-existing out-of-scope Quick Stock feature, not something any Phase 5 commit touched. It remains uncommitted and untouched by this audit. |
| `send_log.json` | Still modified-in-place, uncommitted, untouched by any Phase 5 commit |
| `order-management-client` | Not referenced by any of the three commits' diffs |

**Finding:** git integrity is clean. No destructive operation occurred. No history was rewritten. The three commits are exactly what they claim to be, sitting where they claim to sit.

## 3. Commit-by-commit review (Parts A, C, D)

### `960b3a5` — Desktop rebrand

Files: `electron/main.cjs`, `index.html`, `package.json`, `src/App.jsx`, new `src/assets/nexora-mediq-mark.svg`.

- **`productName`**: `"Axythic Supplier Stock"` → `"NEXORA MEDIQ"` — confirmed in diff and at HEAD.
- **Window title**: `main.cjs` line 238, `title: 'Axythic Supplier Stock'` → `'NEXORA MEDIQ'` — confirmed, single-line change, no other `BrowserWindow` option touched.
- **Document title**: confirmed in `App.jsx` (`document.title` effect).
- **Login/nav/Settings branding**: confirmed, string-literal only, no JSX structure or component boundary changed.
- **SVG asset**: read in full this audit. Valid, well-formed SVG — a hexagonal navy mark (`#1e293b`→`#0f172a` gradient) with a cyan/teal pulse accent (`#22d3ee`/`#0d9488`/`#0891b2`) and a two-line "NEXORA / MEDIQ" wordmark. Matches the stated navy/graphite + restrained cyan/teal brief. No external references, no script content, renders as a static vector mark.
- **Electron security**: `contextIsolation: true` and `nodeIntegration: false` **directly confirmed at HEAD** (lines 242-243) — unchanged by this commit; the diff touches only the adjacent `title:` line.
- **Installer artifact name**: `package.json` `dist` script changed to `NEXORA-MEDIQ-Setup-${version}.${ext}` — confirmed in diff.
- **No internal identifiers renamed**: `appId` (`com.nexora.desktop.stock`), npm `name` (`nexora-supplier-stock-client`) — both confirmed unchanged at HEAD. No backend file appears in this commit's file list.

Classification: every claim in report 24 §1/§3 about this commit is **VERIFIED**.

### `ef4192c` — Device Controller `PRODUCT_NAME` fix

- **Mechanism verified at HEAD**: `PRODUCT_NAME = "NEXORA MEDIQ"`, `_LEGACY_PRODUCT_NAMES = ("Axythic Supplier Stock",)`. `exe()` and `_candidate_dirs()` both iterate `(PRODUCT_NAME,) + _LEGACY_PRODUCT_NAMES`.
- **`update()` dependency on `PRODUCT_NAME` is real and was correctly identified**: `StockClientApp.update()` (line 795) calls `self.exe()` (via `self.version()` and the `current = self.exe()` reinstall-path lookup) before running the staged installer with `/D={current.parent}`. If `exe()` cannot find the current install, `update()` cannot target the in-place reinstall correctly. Report 24 §2's claim that `update()` verifies via `self.version()` (not filename matching) is accurate; it under-states, slightly, that `version()` *itself* calls `self.exe()` first, so the fix is still load-bearing for update, not just start/stop/status as §2's phrasing alone might suggest. This is a nuance, not a contradiction.
- **Ambiguous-match risk (Part D)**: `_candidate_dirs()` returns multiple directories per name and `exe()` takes the *first* match found, in iteration order `(PRODUCT_NAME, "Axythic Supplier Stock")` for each directory before moving to the next directory. On a machine where **both** an old-branded and a new-branded install happen to coexist (e.g. a botched manual install, never expected in normal fleet operation since the installer is per-machine/`perMachine: true` and reinstalls in place), `exe()` would silently prefer whichever name matches first in a given candidate directory, not necessarily the newest. This is a **real but low-probability edge case**, not addressed by report 24, and not addressed by the code — classified below as PARTIALLY VERIFIED risk, not a defect severe enough to block, because normal fleet operation (one NSIS `perMachine` install, reinstalled in place by `update()`) does not produce this state.
- **Version bump**: `CONTROLLER_VERSION` `"1.0.6"` → `"1.0.7"` in `__init__.py` — confirmed, consistent with semantic-looking patch bump for a behavior fix, not inflated to a feature/major version.
- **Report 24 §4 factual inaccuracy found**: §4 states *"A new line is added for the NEXORA MEDIQ-era slug (`nexora-mediq`) alongside the existing ones"*. **This is not what the diff or HEAD show.** There is no `"nexora-mediq"` string anywhere in `apps.py`. The actual fallback added is the *old* slug `axythic-supplier-stock` (already present pre-change, kept, not newly added as claimed) plus the `_LEGACY_PRODUCT_NAMES` tuple iterated against `ProgramFiles`/`LOCALAPPDATA` paths. The functional *outcome* report 24 describes (old and new installs both discoverable during transition) is correct; the specific mechanism described (a new `nexora-mediq` slug line) is not. **Classified INCORRECT** — a real documentation defect, not a code defect.
- **No Device Controller tests exist** (`find` for `*test*` under `device_controller/` returned nothing) — so "inspect relevant Device Controller tests" (Part D) has no evidence to inspect. Report 24 does not claim any test coverage for this change, which is itself consistent with there being none — but it also does not flag the complete absence of controller test coverage as a known gap. **Added here as a new finding, not previously surfaced.**

### `b3b809a` — doc 24 itself

A documentation commit, no source change. Reviewed in full in §4 below.

## 4. Report 24 claim-by-claim verification table (Part B)

| # | Claim (report 24) | Classification | Basis |
|---|---|---|---|
| 1 | `productName`/window title/doc title/login/nav/Settings copy all changed as described | VERIFIED | Direct diff + HEAD read, §3 above |
| 2 | `contextIsolation`/`nodeIntegration` unchanged | VERIFIED | Direct read of `main.cjs` lines 242-243 at HEAD |
| 3 | No backend file modified in Phase 5 | VERIFIED | `git show --name-status` on all 3 commits — zero files under `backend/` |
| 4 | Device Controller is the live fleet updater, Watchdog is legacy/auto-retired | VERIFIED | `LEGACY_WATCHDOG_SERVICES` tuple includes `NexoraStockClientWatchdog`; `retire_legacy_watchdogs` runs on init by default (`cfg.get("retire_legacy", True)`) — confirmed directly in `device_controller/__init__.py` and `service.py` at HEAD |
| 5 | Git log shows Watchdog's last commits predate Device Controller's | VERIFIED | `git log` on both files: Watchdog last touched by `52ad8e3`/`52fa1cd` (original build); `device_controller/apps.py` last touched by `2ec176b` then `ef4192c` (this phase) |
| 6 | `StockClientApp.update()` verifies by installed version, not filename match | VERIFIED (with nuance) | Confirmed at HEAD; nuance noted in §3 — `version()` itself depends on `exe()`, so the §4 fix is load-bearing for update too |
| 7 | A new `nexora-mediq` slug line was added to the fallback probe | **INCORRECT** | No such string exists anywhere in `apps.py` at HEAD or in the diff; see §3 |
| 8 | `PRODUCT_NAME` fix resolves a real, previously-undocumented compatibility blocker | VERIFIED | Confirmed mechanically: electron-builder names the installed exe from `productName`; `apps.py` matched only the old literal before this fix |
| 9 | Watchdog's own filename glob (`Axythic-Supplier-Stock-Setup-*.exe`) left untouched | VERIFIED | `grep` on `stock_client_watchdog_service.py` at HEAD shows only the original Axythic-named glob, unchanged |
| 10 | `node --test` → 61 pass, 0 fail | VERIFIED | Re-run independently this audit, at current HEAD: 61 pass, 0 fail, 0 skipped |
| 11 | `pytest tests/` → 415 passed | VERIFIED | Re-run independently this audit, at current HEAD: 415 passed, 21 warnings (same pre-existing deprecation warnings) |
| 12 | `vite build` succeeded, 113 modules | UNVERIFIED (not re-run this audit) | Not re-executed independently in this pass; no reason found to doubt it (no new import, no module added/removed by this commit's diff beyond the SVG asset, which Vite handles natively) — downgraded from VERIFIED to UNVERIFIED only because this audit did not re-run it, per the instruction not to infer success from report text alone |
| 13 | No Electron packaging / installer build was executed in this phase | VERIFIED | `release/` contains only pre-existing installers numbered 0.1.56–0.1.71, all still Axythic-named; none dated to this session; `release/win-unpacked/Axythic Supplier Stock.exe` is stale, confirming no new packaging ran |
| 14 | No signing key configured; any build would be unsigned | VERIFIED | `package.json` `win` block has `signAndEditExecutable: false`, no `certificateFile`/`certificateSubjectName` key present anywhere in the file |
| 15 | SHA-256 / Ed25519 verification code untouched | VERIFIED | Neither `_verify_package` (Watchdog) nor any Device Controller signing path appears in any of the three commits' diffs |
| 16 | `electron-updater` remains a confirmed no-op | VERIFIED (carried from Phase 1, re-confirmed) | `initAutoUpdates()` body is still a documented no-op in `main.cjs` at HEAD; not touched by any Phase 5 commit |
| 17 | Repository safety items (§12: Quick Stock, `send_log.json`, `order-management-client`, no destructive git ops, external commits intact) | VERIFIED | Confirmed independently in §2 above |
| 18 | Final verdict "PARTIAL" | VERIFIED as an honest self-assessment | Matches this audit's independent §1 verdict for the same underlying reasons |

## 5. Device Controller compatibility assessment (Part D)

**Technically correct for the normal case; untested; one edge case and one documentation error found.**

- The fix addresses a real mechanical break (confirmed in §3/§4).
- Start/stop/update/status all route through the same `self.exe()` call, so the fix is consistent across every operation that needs to find the install — there is no operation left using the old `PRODUCT_NAME` directly (`grep` for the bare string `"Axythic Supplier Stock"` in `apps.py` after the fix returns only the `_LEGACY_PRODUCT_NAMES` tuple value, never a second, un-updated hardcoded copy).
- **No automated test exists for this class at all** — not newly broken by this phase, but newly relevant, since this phase is the first to touch the file's core discovery logic.
- **Ambiguous-match edge case** (§3) is real but low-probability under normal `perMachine` NSIS reinstall semantics.
- **This audit did not start, stop, or update the Stock Client via the Device Controller, and did not connect to any fleet machine** — per the strict boundaries in the authorization. Runtime behavior against a real installed app, old or new, remains **UNVERIFIED** by direct observation; the above is a source-level correctness assessment only.

## 6. Watchdog compatibility assessment (Part E)

Read `stock_client_watchdog_service.py` in full again this audit (not relying on doc 15/24 alone):

1. **Filename matching**: `_apply_update`/`_backup_current`/`_installed_backup_path` all construct or glob `Axythic-Supplier-Stock-Setup-{version}.exe` — a literal f-string/glob, confirmed unchanged at HEAD.
2. **Expected extension**: `.exe`, hardcoded alongside the name — unchanged.
3. **Version extraction**: comes from the HO-provided `target` dict (`target.get("target_version")`), not parsed from the filename — the filename is constructed *from* the already-known version, not parsed back out of it. A rename would not break version extraction; it would break the staged file's *name only* (cosmetic to the Watchdog's own logic) — but see point 9.
4. **SHA-256**: `_verify_package` computes `_sha256_of(path)` against `target.get("sha256")` — independent of filename, confirmed unaffected by any naming change.
5. **Ed25519**: `crypto.verify(public_pem, manifest, signature)` where `manifest = f"{version}|{sha256}|{size}"` — also independent of filename, confirmed unaffected.
6. **Public key handling**: read from `STATE_DIR` or a bundled fallback path — unrelated to product naming, unaffected.
7. **Failure behavior**: a `RuntimeError` on either mismatch, caught in `run_once`'s `except Exception` with `last_status = "update-failed"` and logged — unaffected by naming.
8. **Install/recovery path**: `UPDATE_MARKER`, `_recover_interrupted`, `_rollback` — all keyed by `STATE_DIR` (`ProgramData/Axythic/StockClient`, itself unchanged) and the backup glob pattern — unaffected by the `productName` rename *as long as the Watchdog process never runs on a given machine*, which §2's finding establishes is the operative condition fleet-wide.
9. **Compatibility with `NEXORA-MEDIQ-Setup-*` filename**: **Not compatible, and not claimed to be.** If the legacy Watchdog were ever polling a machine that receives a `NEXORA MEDIQ`-branded package, it has no code path that would ever construct or look for that filename — it only ever builds `Axythic-Supplier-Stock-Setup-{version}.exe`. This is accurately described in report 24 §2/§5 as a known, deliberate, unaddressed divergence for a component asserted to be dead on every Device-Controller-managed PC. **This audit did not independently verify that claim against a live fleet machine** (explicitly out of bounds) — it rests on source inspection (`retire_legacy_watchdogs`) and the prior session's fleet-operations memory citations in report 24 §2, which this audit cannot re-verify from inside the repository. **Classified PARTIALLY VERIFIED**: the retirement *mechanism* is verified in source; its *effect having actually happened on every real fleet machine* is not something this audit can observe.

No safe local test could establish "Watchdog accepts a NEXORA-MEDIQ-named package" without either modifying the Watchdog's source (out of bounds) or fabricating a fake signed package (requires a private signing key this environment does not have, and would not prove anything about production keys regardless) — correctly not attempted.

## 7. Test and build evidence (Part F)

| Command | Evidence | Exit | Result | Ran against |
|---|---|---|---|---|
| `node --test src/*.test.js src/state/*.test.js` | Re-run live, this audit | 0 (process completed, `fail 0`) | 61 pass / 0 fail / 0 skipped | Current HEAD (`b3b809a`) |
| `pytest tests/ --tb=short` | Re-run live, this audit | 0 | 415 passed, 21 warnings | Current HEAD (`b3b809a`) |
| `vite build --mode development` | Not re-run this audit | — | UNVERIFIED this pass (report 24 claims 113 modules, no errors) | N/A |
| `npm run dist` / electron-builder | No evidence found; `release/` contains only pre-existing artifacts, none from this session | — | Confirmed NOT executed | N/A |
| Installer artifact validation | No new artifact exists to validate | — | Confirmed NOT executed | N/A |
| Watchdog compatibility test | No test exists; source-only analysis performed (§6) | — | NOT a runtime test; source review only | HEAD |

## 8. Installer artifact inventory (Part G.9)

`release/` contains 16 installer `.exe`/`.blockmap` pairs, versions 0.1.56 through 0.1.71, **all pre-dating Phase 5**, all still carrying the `Axythic-Supplier-Stock-Setup-` filename prefix. `release/win-unpacked/` contains a stale unpacked build (`Axythic Supplier Stock.exe`) from the last real packaging run, also pre-Phase-5. **No `NEXORA-MEDIQ-Setup-*` artifact exists anywhere in the repository.** This matches report 24's own statement that packaging was not run; it is independently confirmed here, not merely repeated.

## 9. Signing status

No certificate file, subject name, or signing tool configuration exists in `package.json`'s `win` block (`signAndEditExecutable: false`, no `certificateFile`/`certificateSubjectName`/`rfc3161TimeStampServer` keys). No signing key material was found, generated, or exposed by any of the three commits. Any future packaging run in this environment produces an unsigned engineering build by construction — a pre-existing environment condition, not introduced or changed by Phase 5.

## 10. Production deployment status

None. No publish, no push to any update feed, no connection to any store PC or HO instance, no fleet-management operation invoked. Confirmed by the absence of any such command in either commit's diff and by this audit's own compliance with its own read-only boundary (no `device_controller` start/stop/update/publish action was invoked).

## 11. Risks and unresolved questions

1. **Report 24 §4 contains a factual inaccuracy** (the "`nexora-mediq` slug" claim) — low severity (the actual fallback logic is sound; only the written description of it is wrong) but should be corrected so the document remains a trustworthy record.
2. **Zero test coverage for `device_controller/apps.py`**, now true of a file this phase's fix made load-bearing for the rebrand's fleet-safety story. Not a regression this phase introduced, but a pre-existing gap this phase's own change makes more consequential.
3. **Ambiguous dual-install edge case** in `StockClientApp.exe()` (§3/§5) — unaddressed, low probability, not previously documented anywhere.
4. **The claim that the Watchdog is inactive fleet-wide rests on prior-session memory citations this audit cannot independently re-verify** from inside the repository (no access to live fleet state) — a reasonable basis for the claim, but not the same thing as direct observation.
5. **No independent re-run of `vite build` in this audit** — recommend re-running before treating "builds cleanly" as current fact rather than prior report.

## 12. Recommended corrections

- Correct report 24 §4's description to match the actual diff (the fallback is the retained old literal `axythic-supplier-stock` plus the `_LEGACY_PRODUCT_NAMES` tuple — no `nexora-mediq` slug string was added).
- Add a note to report 24 (or a new tracked item) recording the complete absence of `device_controller` test coverage as a known gap, not just the absence of *new* tests for this specific change.
- Consider whether the dual-install ambiguity in `exe()` is worth a defensive ordering fix (prefer `PRODUCT_NAME` matches over legacy matches **within the same directory**, which the code already does correctly — the ambiguity is only across *different* candidate directories, e.g. an old ProgramFiles install plus a new LOCALAPPDATA install coexisting) before accepting this as permanently fine, even though the authorization's scope here was read-only and this is flagged rather than fixed.

## 13. Final Phase 5 verdict

**PARTIAL.**

Reached independently, not inherited from report 24. Grounds: the rebrand and the Device Controller fix are real, source-verified, and currently pass the full existing test suite (re-run live during this audit, not merely trusted). They are also properly and honestly scoped — report 24 does not claim packaging, signing, or installer-level validation that didn't happen, and this audit confirms none of those occurred. The one accuracy defect found (§4/§11.1) is in the report's prose, not in the underlying code or its test results. No critical safety or compatibility defect was found that would justify BLOCKED.

## 14. Outstanding actions required before Phase 6

1. Correct report 24 §4's inaccurate description (documentation-only fix, no source change required).
2. Independently re-run `vite build` before relying on "113 modules, no errors" as current fact.
3. Decide whether a packaging/signing/installer-validation pass happens as its own explicit, reviewed step (as report 24 itself recommends) before any Phase 6 authorization.
4. Treat the complete absence of Device Controller test coverage as carry-forward technical debt, now elevated in priority since this phase made `apps.py`'s discovery logic load-bearing for the rebrand's safety story.
5. No fleet-facing action (packaging, signing, publishing, or any live Device Controller operation) should be taken without a further, explicit authorization — none of this audit's findings change that standing boundary.
