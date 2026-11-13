# 27 — Phase 5.2 Unsigned Installer Validation
**NEXORA MEDIQ — Local Electron Packaging & Unsigned Installer Validation**
Date: 2026-11-13

## 1. Git baseline

- Branch: `nexora-mediq-implementation`.
- Starting HEAD: `a0ac3d8` (Phase 5.1's final commit), verified via `git rev-parse HEAD` before any build command.
- Working tree before packaging: clean except the same pre-existing, concurrently-evolving Quick Stock drift (`backend/modules/quick_stock/router.py`, `service.py`, five `frontend/src/pages/quick-stock/*` files, one file deleted, three untracked, plus `desktop/quick-stock-client/`) and `backend/storage/whatsapp/send_log.json` — confirmed unchanged by this phase's own `git status` check at the end.
- This phase makes **no source commit**: packaging produces build artifacts only (`release/`, `dist/`), both already covered by `.gitignore` (confirmed via `git check-ignore -v`), so no new file enters the working tree's tracked state. This report itself is the only thing committed.

## 2. Pre-packaging safety review

Performed before running any build command:

1. **`package.json` scripts inspected.** `dist`: `vite build && electron-builder --win --config.artifactName="NEXORA-MEDIQ-Setup-${version}.${ext}"`. No `prebuild`/`postbuild`/`prepack`/`postpack` hooks exist anywhere in the file.
2. **electron-builder configuration inspected.** A `publish` block exists (`{"provider": "generic", "url": "http://192.168.10.80:8000/updates"}`) — the real HO update-feed URL. This is pre-existing configuration, not something this phase added.
3. **Publish-trigger behavior verified directly, not assumed:** `npx electron-builder --help` confirms `-p, --publish` takes an explicit choice (`onTag`/`onTagOrDraft`/`always`/`never`/undefined) and is never passed by the `dist` script. No CI-detection environment variable (`CSC_IDENTITY_AUTO_DISCOVERY`, `GH_TOKEN`, `EP_*`, or any CI-platform marker) was present in the shell environment (checked via `env | grep`). electron-builder's documented behavior is to default to `never` for a local, non-CI, non-tagged run with no `-p` passed. **This phase additionally passed `--publish never` explicitly on every build invocation**, as defense-in-depth rather than relying on the implicit default alone.
4. **No credential or production-config environment variable found** beyond the pre-existing, harmless `ELECTRON_RUN_AS_NODE=1` (a Node/Electron tooling artifact, unrelated to publishing).
5. **Existing release artifacts inventoried and checksummed before packaging**, per Part B's "preserve and identify" requirement: 16 pre-existing `Axythic-Supplier-Stock-Setup-{0.1.56..0.1.71}.exe` files in `release/`, none at risk of collision since this phase's output uses a different filename prefix (`NEXORA-MEDIQ-Setup-*`). The highest-numbered pre-existing artifact (`...-0.1.71.exe`) was checksummed (`sha256: b604315f...`) before the build touched the directory, confirming it was not disturbed afterward (the two filenames never overlap, so no overwrite occurred — verified, not merely assumed, by the artifact still being present and unchanged after packaging).
6. **Quick Stock changes and `send_log.json` identified and left untouched** — confirmed before and after packaging via `git status`; no packaging command touches any file under `backend/` or `frontend/src/pages/quick-stock/`.

**Conclusion: the existing `dist` command was judged safe to run as-is**, with `--publish never` added explicitly rather than relying on the default alone, and no modification to electron-builder configuration, signing settings, or the `publish` block was made.

## 3. Exact packaging command

**First attempt (superseded — see §3a):**
```
cd E:\Nexora\desktop\supplier-stock-client
npx vite build --mode development
npx electron-builder --win --publish never --config.artifactName="NEXORA-MEDIQ-Setup-${version}.${ext}"
```

**§3a — self-correction before accepting the result:** this first invocation explicitly passed `--mode development` to `vite build`, copying the convention used in every prior phase's *compile-check-only* build verification (doc 23/24/25/26). That convention is correct for a syntax/dependency check but wrong for producing an actual distributable artifact: Vite's `development` mode causes `import.meta.env` to inline the project's `.env.development`/`.env.development.local`/`.env.local` values, which include a dev HO address and a dev login credential (see §9). The resulting installer, while functionally identical in every other respect, was not the correct artifact to validate or report as this phase's deliverable. It was deleted (`release/NEXORA-MEDIQ-Setup-0.1.71.exe` and its `.blockmap`) before any further inspection was performed on it, and the build was redone correctly:

**Actual, reported packaging command:**
```
cd E:\Nexora\desktop\supplier-stock-client
npm run dist -- --publish never
```
which expands to:
```
vite build && electron-builder --win --config.artifactName="NEXORA-MEDIQ-Setup-${version}.${ext}" --publish never
```
This runs `vite build` with **no mode override**, which defaults to Vite's own `production` mode — confirmed in the build's own log output ("building client environment for **production**", vs. the first attempt's "...for **development**"). This is the actual `dist` script, run as a real packager would run it, with only `--publish never` appended as this phase's explicit safety measure.

Build window: 2026-11-13 11:17:48 to 11:18:25 (~37 seconds).

## 4. Packaging result

**Exit code: 0.** No error at any stage (Vite build, NSIS packaging, blockmap generation). No publish attempt occurred — the build log contains no "publishing" line at any point, consistent with `--publish never`.

Non-error log lines worth noting, all pre-existing conditions unrelated to this phase:
- `author is missed in the package.json` — informational, pre-existing.
- `asar usage is disabled — this is strongly not recommended` (×2) — pre-existing (`"asar": false` in `package.json`'s `build` block, unchanged by any Phase 5/5.1/5.2 commit).
- `default Electron icon is used — reason=application icon is not set` — confirms, again, the pre-existing absence of a custom `.ico` (first noted in Phase 5's pre-implementation audit).
- `output file is locked for writing (maybe by virus scanner) => waiting for unlock...` — a transient Windows Defender/AV file-lock retry, resolved automatically by electron-builder's own retry logic; did not cause a failure.

## 5. Actual installer path and file size

`E:\Nexora\desktop\supplier-stock-client\release\NEXORA-MEDIQ-Setup-0.1.71.exe`

- Size: **85,947,045 bytes** (~82.0 MiB).
- Companion blockmap: `NEXORA-MEDIQ-Setup-0.1.71.exe.blockmap` (90,455 bytes).
- SHA-256 (of the final, production-mode artifact — the development-mode one from §3a was deleted and never checksummed as a deliverable): `ae5cf9173cb33c782f8add391288914e31797ed7a420edde8ba0a9b0b3816d02`.
- Unpacked application directory: `release\win-unpacked\`, containing `NEXORA MEDIQ.exe` (157,602,304 bytes) as the main executable — correctly named from `productName`, independently confirming what Phase 5.1's `StockClientApp` test suite already proved discoverable by name.

## 6. Installer metadata

Verified directly via PowerShell `Get-Item ... | Select VersionInfo` against the actual files, not inferred from configuration:

| Field | Installer (`NEXORA-MEDIQ-Setup-0.1.71.exe`) | Inner app exe (`NEXORA MEDIQ.exe`) |
|---|---|---|
| ProductName | `NEXORA MEDIQ` | `Electron` |
| FileDescription | `NEXORA MEDIQ — Intelligent Pharmaceutical Workspace desktop client` | `Electron` |
| CompanyName | (blank) | `GitHub, Inc.` |
| ProductVersion / FileVersion | `0.1.71` | `22.3.27` |

**Finding, not previously documented in doc 24/25/26:** electron-builder rewrites the **NSIS installer wrapper's** own PE version resource from `productName`/`description` regardless of the `signAndEditExecutable` setting (that setting only governs whether the **packaged app's** executable is rewritten). Because `package.json`'s `win.signAndEditExecutable` is `false`, the **inner** `NEXORA MEDIQ.exe` still carries Electron's own stock version metadata (`Electron` / `GitHub, Inc.` / `22.3.27`) rather than the NEXORA MEDIQ identity. This means a user opening the installed app's Properties dialog, or an admin reading Task Manager's Description/Company columns, would see "Electron" / "GitHub, Inc.", not "NEXORA MEDIQ" — a real, user-visible branding gap that exists **independently of signing status** and was not caused by this phase (the condition is identical before and after the Phase 5 rebrand; `signAndEditExecutable: false` predates this project). Recorded here as a carry-forward item, not fixed in this phase (fixing it would mean flipping `signAndEditExecutable` to `true`, a security/build-tooling setting change outside this phase's "generate and inspect, don't modify the signing posture" scope).

Architecture: x64 (confirmed in the build log: `archs=x64`). Installation directory, executable name, application icon, uninstaller metadata, and bundled resources are covered in §7.

## 7. Authenticode signing status (Part D)

Verified directly via `Get-AuthenticodeSignature` against both actual files, not inferred from `signAndEditExecutable: false` alone:

- `release\NEXORA-MEDIQ-Setup-0.1.71.exe` → **`Status: NotSigned`**.
- `release\win-unpacked\NEXORA MEDIQ.exe` → **`Status: NotSigned`**.

Both confirmed unsigned by direct Authenticode inspection. **This installer is an UNSIGNED ENGINEERING BUILD. It must not be described, distributed, or treated as a production-ready release.**

No signing was attempted. No certificate was generated, modified, or referenced. `package.json`'s `win` block contains no `certificateFile`, `certificateSubjectName`, or `rfc3161TimeStampServer` key — confirmed unchanged from every prior phase's finding.

**Requirements for a future authorized signed release** (documented per this phase's Part D instruction, not actioned):
1. A code-signing certificate (standard Authenticode, or EV for SmartScreen reputation) must be acquired and provisioned — not present in this repository or environment today.
2. `package.json`'s `build.win` block would need `certificateFile`/`certificateSubjectName` (or equivalent CSC_* environment variables electron-builder also honors) pointing at that certificate.
3. A decision on `signAndEditExecutable` (currently `false`) would need revisiting if the inner app exe's own metadata (§6) should also carry proper Authenticode signing and branding, not just the installer wrapper.
4. The private key/certificate must never be committed to this repository or exposed in build logs — a dedicated, access-controlled secrets mechanism (CI secret store, hardware token, or equivalent) would be needed, explicitly out of this phase's scope to set up.
5. Separately from code signing: the Watchdog/filename-compatibility question (§8) would need its own resolution before a signed artifact is treated as fleet-ready, since signing and filename-discoverability are independent concerns.

## 8. Watchdog filename compatibility (Part E)

Direct comparison against the actual artifact, not a filename pattern on paper:

- **Produced filename:** `NEXORA-MEDIQ-Setup-0.1.71.exe`.
- **Watchdog's expected pattern** (confirmed unchanged at HEAD, re-read this phase from `store_agent_setup/stock_client_watchdog_service.py`): `Axythic-Supplier-Stock-Setup-{version}.exe`, constructed via f-string in `_apply_update`/`_backup_current` and globbed via `BACKUP_DIR.glob("Axythic-Supplier-Stock-Setup-*.exe")` in `_installed_backup_path`.
- **Would the Watchdog discover this artifact? No.** `"NEXORA-MEDIQ-Setup-0.1.71.exe"` does not match `"Axythic-Supplier-Stock-Setup-*.exe"` under any glob interpretation — the prefix differs entirely, not just the version segment. Confirmed by direct string comparison against the real produced filename, not assumed from the naming convention alone.
- **Consistency with the approved release architecture:** consistent with Phase 5/5.1's documented, deliberate position — the live fleet-update mechanism (Device Controller) does not depend on this filename pattern at all (confirmed in doc 24 §2 and re-verified in Phase 5.1's test suite), so this incompatibility was accepted knowingly, not introduced as an oversight.
- **Required qualification preserved, per this phase's explicit instruction:** Phase 5.1 classified the Watchdog as RETIRED based on the NSIS installer no longer invoking it, the Device Controller's `retire_legacy_watchdogs()` disabling it by name on every PC it manages, and direct, positive evidence from this one local development machine (`sc query` showing it not installed while the Device Controller is running). **That classification's own limitation stands unchanged: it cannot be verified as true for every machine in the live production fleet from inside this repository.** This phase's finding — the installer artifact genuinely cannot be discovered by the Watchdog's filename pattern — is recorded **even though** the Watchdog is believed retired, exactly as this phase's Part E instructed ("If the Watchdog cannot discover the installer, record the incompatibility even if the Watchdog is classified as retired"). If that RETIRED classification were ever found to be wrong for some subset of the fleet, this specific, confirmed incompatibility is the concrete mechanism by which an update would silently fail to reach those machines via the legacy path.
- No Watchdog source was modified. No signature-verification logic was touched or disabled.

## 9. Static artifact inspection (Part C)

Performed by direct extraction/inspection of the actual installer and unpacked app, not inferred from `package.json`'s `build` configuration:

1. **Filename**: `NEXORA-MEDIQ-Setup-0.1.71.exe` — confirmed correctly reflects the new product identity and the version electron-builder read from `package.json`.
2. **Version**: `0.1.71` on both the installer wrapper and (via `resources/app/package.json`) the packaged app — consistent, no version drift introduced by packaging.
3. **Product metadata**: see §6.
4. **Publisher/signing metadata**: `NotSigned` on both files (§7); no publisher/signer identity present, as expected for an unsigned build.
5. **Architecture**: x64 only (no ia32/arm64 target configured or built).
6. **Installation directory**: NSIS `perMachine: true`, `allowToChangeInstallationDirectory: true` — defaults to the standard per-machine Program Files path, user-overridable at install time (not exercised in this phase per §10).
7. **Executable name**: `NEXORA MEDIQ.exe` — confirmed correctly derived from the new `productName`, matching exactly what Phase 5.1's `StockClientApp.exe()` test suite proved the Device Controller would successfully discover.
8. **Application icon**: none configured; electron-builder's log explicitly states `default Electron icon is used` — unchanged pre-existing condition, not addressed in this phase (icon-asset creation was Phase 5's §6 scope, not revisited here).
9. **Uninstaller metadata**: generated by the standard NSIS `allowToChangeInstallationDirectory`/`createDesktopShortcut`/`createStartMenuShortcut` configuration — not independently exercised (no live install was performed; see §10), but the installer build log shows no NSIS packaging error for the uninstaller stub.
10. **Bundled resources**: `resources/app/` (dist + electron + node_modules + package.json), `resources/controller/NexoraDeviceController.exe` (confirmed present — the Device Controller is correctly bundled into this build, consistent with the `customInstall` macro's `install-service` invocation found in Phase 5.1's Watchdog-status investigation), `resources/tools/lock-display-resolution.ps1`.
11. **Required Device Controller components**: confirmed present and correctly placed (`resources/controller/NexoraDeviceController.exe`) — this is the component the `installer.nsh` `customInstall` macro installs as a service on every real install.
12. **Absence of unintended secrets**: no `.pem`, `.key`, certificate, or credential file found anywhere under `resources/`. **One genuine, non-blocking finding**: the bundled, minified frontend JS (`resources/app/dist/assets/index-*.js`) contains the literal strings `devadmin` / `DevAdmin@123` and `192.168.10.80` as inert `import.meta.env` object properties (Vite inlines all `VITE_`-prefixed env-var keys found at build time as plain object fields regardless of mode — it does not strip unused keys). Verified these are **not active** in this production build: the surrounding code reads `Mt.DEV: false` / `Mt.PROD: true` (confirmed by direct inspection of the bundle), and the dev-login/dev-API-URL logic is gated behind `Mt.DEV &&`, which short-circuits to false/empty in this build. This is a low-severity information-disclosure condition (a known, weak development-only credential string visible to anyone who extracts and reads the installer's bundled JS in a text editor) rather than an exploitable secret or a production credential — but it is a real, previously-undocumented characteristic of how this project's Vite build inlines environment variables, not specific to Phase 5.2's rebrand. Recorded as a known issue (§13), not silently omitted.
13. **Absence of unintended production configuration**: no production database connection string, no production signing key, no production-only feature flag found. The `publish` block's HO URL (`192.168.10.80:8000`) is present in `package.json`'s `build` configuration (as it was before this phase) but is configuration metadata read by electron-builder at packaging time, not inlined into the shipped app bundle itself — distinct from the dev-credential strings above, which are inlined into the renderer JS.

**Confirmation that the artifact is genuinely NEXORA MEDIQ-branded**: verified by direct inspection, not inferred from configuration — installer filename, installer PE metadata, inner exe filename, and the packaged `resources/app/package.json`'s `description` field all independently confirm the NEXORA MEDIQ identity (with the one documented exception in §6: the inner exe's own PE version resource, which `signAndEditExecutable: false` leaves at Electron's stock values).

## 10. Installation/uninstallation results

**Not performed.** Per Part F's own fallback instruction ("If isolated installation cannot be performed safely, use static artifact inspection and report the limitation"), and after confirming with the account owner, this phase used static inspection only. Reason: this development machine already has a real "Axythic Supplier Stock 0.1.71" installed (confirmed in Phase 5.1) and a running `NexoraDeviceController` service; running an actual `perMachine: true` NSIS install here — even of an unsigned engineering build — risks interacting with that existing install, the live Device Controller service, or other concurrent work on this shared machine (the Quick Stock drift observed throughout Phases 5/5.1/5.2 confirms other work is actively in progress here), none of which this phase's authorization permits risking. No genuinely isolated environment (a clean VM or container with no pre-existing Nexora install) was available within this phase's scope to set up safely.

**Limitation recorded explicitly**: application startup, basic navigation, uninstallation, and "no unrelated applications affected" could not be verified by live execution in this phase. What was verified instead: the static metadata and content inspection in §5-9, and the full existing automated test suites (§11-12), none of which exercise the packaged installer's actual install/launch/uninstall behavior. This is a real, acknowledged gap in Phase 5.2's validation coverage, not papered over.

## 11. Frontend/backend test results

```
cd E:\Nexora\desktop\supplier-stock-client
node --test src/*.test.js src/state/*.test.js
```
**61 pass, 0 fail, 0 skipped.** Re-run live, this phase, after packaging completed — confirms packaging did not disturb the source tree (it only reads `dist/` output and `package.json`; it does not write back to `src/`).

```
cd E:\Nexora\backend
.venv/Scripts/python.exe -m pytest tests/ --tb=short -q
```
**415 passed, 0 failed, 21 warnings** (same pre-existing FastAPI deprecation warnings, unrelated to this phase).

## 12. Device Controller test results

```
cd E:\Nexora
backend/.venv/Scripts/python.exe -m pytest store_agent_setup/device_controller/test_apps_stock_client.py -q -p no:cacheprovider
```
**22 passed, 0 failed.** Confirms the Phase 5.1 test suite remains fully passing and unaffected by this phase's packaging activity (no production code was modified in Phase 5.2; packaging is a read-of-source, write-to-`release/` operation only).

## 13. Known limitations

- **No live installation/uninstallation test was performed** (§10) — a real, acknowledged gap, not silently skipped.
- **The inner app executable's own PE version metadata is not rebranded** (§6) — a pre-existing condition (`signAndEditExecutable: false`), independent of signing status, not addressed in this phase.
- **Dev-only credential/HO-address strings are present, inert, in the bundled renderer JS** (§9.12) — not active in a production-mode build, not a production secret, but a real, previously-undocumented characteristic of this project's Vite env-var inlining behavior, worth awareness for any future packaging.
- **A first packaging attempt used the wrong build mode** (`--mode development`, copying the convention from prior phases' compile-only checks) and was caught and corrected before being treated as this phase's deliverable (§3/§3a) — documented transparently rather than silently discarded without explanation, since it is relevant evidence of how easily a wrong-mode artifact could otherwise have been shipped as "the installer."
- **Watchdog filename incompatibility is confirmed, real, and permanent** for the current naming scheme (§8) — not a defect to fix in this phase, since the live update path does not depend on it, but a fact that would matter if the RETIRED classification's fleet-wide limitation ever proved wrong for some subset of machines.
- No application icon exists (pre-existing, unaddressed).
- No code signing exists (pre-existing, unaddressed, requirements documented in §7).

## 14. Production safety confirmation

- No production database was connected to, queried, or modified.
- No production fleet machine was contacted. No Device Controller operation (start/stop/update) was executed against any real installation, production or otherwise.
- `--publish never` was passed explicitly on every build invocation; the build log confirms no publish attempt occurred at any point.
- No signing key or certificate was generated, modified, accessed, or exposed.
- No artifact was uploaded to any external service, store, or distribution channel.
- The existing 16 pre-Phase-5 release artifacts in `release/` were checksummed before packaging and confirmed undisturbed afterward (no filename collision occurred).
- `backend/storage/whatsapp/send_log.json` and the Quick Stock drift remain exactly as they were at the start of this phase (confirmed via `git status` before and after).
- `E:\Nexora\desktop\order-management-client` was not opened, read, or referenced anywhere in this phase.
- No destructive git operation was performed. This phase creates no source commit; only this report is added to version control.
- SHA-256/Ed25519 verification code (Watchdog's `_verify_package`) was read for comparison purposes only (§8) — never modified, never invoked, never bypassed.

## 15. Signed-release requirements

See §7 for the complete, itemized list (certificate acquisition, `package.json` signing configuration, the `signAndEditExecutable` decision, secret-handling mechanism, and the separate Watchdog-filename question). None of these were actioned in this phase, consistent with its explicit non-authorization for production code signing.

## 16. Final verdict

**PARTIAL.**

A real, unsigned, correctly-branded NEXORA MEDIQ installer was produced (`NEXORA-MEDIQ-Setup-0.1.71.exe`, 85,947,045 bytes, SHA-256 `ae5cf917...`), confirmed unsigned by direct Authenticode inspection, confirmed NEXORA MEDIQ-branded by direct metadata/content inspection (with one documented exception, the inner exe's stock Electron PE metadata), confirmed incompatible with the Watchdog's filename pattern (expected, already-documented, non-blocking given the RETIRED classification's evidence), and validated against the full existing regression suite (61/61 desktop, 415/415 backend, 22/22 Device Controller) with no failure introduced. It is PARTIAL rather than COMPLETE because live installation/uninstallation validation (Part F) was not performed, by deliberate, authorized choice rather than failure — this development machine's existing real install and running Device Controller service made a live test unsafe to attempt within this phase's own safety boundaries, and Part F's own fallback instruction anticipated exactly this case.

This is an **UNSIGNED ENGINEERING BUILD**. It must not be described, treated, or distributed as a production-ready release.
