# Axythic Mobile — Session Handoff

**Read this first when resuming work on the Axythic mobile app.**
Last updated: 2026-08-19 · Branch: `bharath-develop`

Full implementation plan: `~/.claude/plans/hiii-bro-atomic-pillow.md`

---

## ▶ RESUME HERE

**Current as of 2026-08-19. Everything since commit `8fe5fd2` is uncommitted
and lives in the working tree — see §5.**

### 60-second orientation

This is **not a web app** — it is a Flutter mobile client (`mobile/`) plus a
FastAPI backend (`backend/`) that already serves a React web console. Mobile is
a *client* for existing server modules; the only backend code added so far is
the additive `backend/modules/mobile_bff/`.

Phases are **not sequential in practice**. Work was pushed forward at the
user's direction while earlier phases were still open. As of 2026-08-18 they
have been walked in order and closed: what remains open in Phases 0–3 is
blocked on the user (§1), not on code.

| Phase | State |
|---|---|
| 0 Setup | 🟡 CI, signing config, OpenAPI snapshot, HTTPS-only release done · **TLS / a real keystore / store accounts need you** |
| 1 Foundation | ✅ unlock-on-open, offline banner and local crash capture done |
| 2 OCR Capture | ✅ code-complete · **exit criterion blocked on a backend bug, §1.4** |
| 3 Core Ops | ✅ Sync Live, Reports, Supplier, outbox, Settings, report cache · **workmanager tick deliberately skipped, see §2** |
| 4 Procurement | ✅ Pass Gen, Time Report, Cycle Console and **Legacy Order Console** done |
| 5 Field Procurement | ✅ Purchase Workspace, Refresh Compare, Stock Distribution and procurement conflict resolution done |
| 6 Release Hardening | 🟡 in progress · platform security, R8/resource shrinking, shared-widget accessibility, store-copy drafts and CI readiness checks done · **profiling, hardware audit, signed distribution and staged rollout remain** |

### First commands to run in a new session

```bash
cd mobile
dart run build_runner build --delete-conflicting-outputs   # generated sources are gitignored
flutter analyze --fatal-infos                              # expect: No issues found
flutter test                                               # expect: 470 passed
```

If `build_runner` is skipped the tree will not compile — `*.g.dart` and
`*.freezed.dart` are not in git.

### The three things that will bite you

1. **A themed button cannot be a direct child of a Row or Wrap** — §3.8. It
   asserts at *paint* time and `analyze` passes it. This has been hit twice.
2. **`testWidgets` runs in fake async** — §3.11 and §3.11a. Awaiting real
   file/Drift I/O in a test body deadlocks the whole file with zero output at
   0% CPU, and so does feeding a widget from a live Drift `watch()` stream.
   Both look exactly like a hung compile. Feed screens plain rows through
   provider overrides.
3. **Verify by running, not analysing.** Every session so far, the integration
   test on a simulator caught something `analyze` and unit tests passed
   straight through. Run it — and boot the simulator fully first, or the
   install fails with a misleading "malformed plist" error.

### Highest-value next steps, in order

1. **Decide on §1.4 — the missing column defaults.** One `--apply` unblocks the
   Phase 2 exit criterion, which is otherwise finished and scripted. Until then
   document capture cannot work against this database at all, and 93 other
   tables carry the same latent fault.
2. **Rotate the leaked JWT secret (§1.1).** Still outstanding, still the highest
   severity item in this document.
3. **Continue Phase 6:** profile on representative phones, finish the screen-level
   accessibility audit, validate minified plugin flows on hardware, then prepare
   signed internal-distribution builds and store screenshots.

**Nothing ships until TLS is up (§1.2), regardless of which of these is done.**

### Suggested opening message for the next chat

Paste this, filling in the last line:

> Read `docs/AXYTHIC_MOBILE_HANDOFF.md` end to end before doing anything — it is
> the full state of this project and supersedes anything you infer from the
> code. Then run the four commands in "First commands to run in a new session"
> to confirm the tree is green (expect 470 tests passing, analyze clean).
>
> Context you need that is not obvious: the mobile app uses the HO backend at
> `http://122.252.246.181:8443`, including on physical Android devices. Login
> `superadmin`. Tenant `a7eb45bd-bdd7-4ee6-bd7b-61d1c7f4305d`
> (Nathan Medicals). Phases 0–5 are done bar the items in §1;
> Phase 6 is in progress.
> Nothing since commit `8fe5fd2` is committed, and §7 says do not commit without
> being asked.
>
> Continue with: <the item you want — see §6>.

---

## 0. Read-this-first facts

Four things that are not obvious from the code and that shaped every decision:

1. **This is not greenfield.** A Flutter app already existed at `mobile/` before
   any of this work — auth, store selection, Drift/SQLite, a full sync engine
   (queue, delta processor, conflict handler, retry policy), Riverpod, Dio,
   go_router. We extend it; we do not rebuild it.
2. **The OCR engine already exists server-side.** `backend/modules/document_extraction/`
   is a 10-stage PaddleOCR pipeline behind 27 endpoints with a *frozen* 5-sheet
   Excel contract (`docs/Document_Extraction_Excel_Contract.md`). Mobile is a
   **client** for it, never a reimplementation.
3. **`/api/pass-gen` is not a gate pass.** It mints store passcodes for the
   field ordering app.
4. **There is no Supplier screen anywhere in the web app.** That module is
   genuinely net-new for mobile.

### Confirmed product decisions (do not re-litigate)

| Decision | Choice |
|---|---|
| Foundation | Extend the existing Flutter app at `mobile/` |
| Scope | Field-first companion, **not** web parity |
| Backend | Add a mobile BFF at `/api/mobile/v1`; leave existing endpoints untouched |
| OCR | Stays server-side (PaddleOCR); the phone captures, reviews and exports |
| Theme | **Dark only.** No light theme, no toggle |

---

## 1. 🔴 UNRESOLVED — action required from the user

### 1.1 Leaked production JWT secret (CRITICAL)

`backend/config/ho.env` was **tracked in a public GitHub repo**
(`JanaPonnusamy/nexora_` — verified public, unauthenticated `HTTP 200`) from
commit `b42e25d` (2026-08-06). It contained a live 64-char `UNINEX_JWT_SECRET`
and a 31-char `UNINEX_SETUP_PASSWORD`.

Why it is full compromise, not just a leaked string:
`config/security.py:47` `decode_access_token()` validates **signature and expiry
only**; `dependencies/auth.py:17` `get_current_user()` returns those claims *as
the user* with **no database lookup**; `dependencies/auth.py:45`
`has_full_access()` reads
`is_platform_user` / `role_names` straight off the token. Anyone with that
secret can sign a super-admin token for a user that does not exist, against a
backend on a public IP over cleartext HTTP.

**Done:** commit `b192104` untracked the file and added a `*.env` ignore rule.
The file is regenerated per-install by `ho_setup/ho_config.py:147`, so
deployments are unaffected.

**Still outstanding — the user must do these:**
- [ ] **Rotate `UNINEX_JWT_SECRET` on the HO server.** Until then the value is
      still in git history and still valid. This is the fix that matters.
- [ ] Rotate `UNINEX_SETUP_PASSWORD` and the SQL `sa` password
      (`Admin123`, also in `SETUP_COMMANDS.md` and `docker-compose.yml`).
- [ ] Audit `dbo.audit_logs` for `auth.login.success` rows whose actor is not in
      `dbo.users`, and unfamiliar IPs since 6 Aug.

### 1.2 TLS — blocks all release work

Everything points at `http://122.252.246.181:8443`. Android 9+ and iOS ATS block
cleartext. **No store release is possible until the HO server serves HTTPS.**
This is the single biggest blocker in the whole plan.

The client side of it is now done — release builds cannot speak cleartext at
all, and a prod build configured with an `http://` URL fails at startup naming
the URL instead of silently failing every request (§2, Phase 0). None of that
substitutes for the server change; it only means the app stops pretending the
configuration is viable. When TLS lands, point `NEXORA_API_BASE_URL` at the
HTTPS host and delete
`mobile/android/app/src/debug/res/xml/network_security_config.xml`.

### 1.3 Blocked on user input

- **Release keystore** — the signing config is now built and tested; what is
  missing is the keystore itself. Generate one, fill in
  `mobile/android/key.properties` from `key.properties.example`, and add
  `AXYTHIC_KEYSTORE_BASE64` / `_PASSWORD` / `AXYTHIC_KEY_ALIAS` /
  `AXYTHIC_KEY_PASSWORD` to the repo secrets — CI picks them up with no workflow
  edit. **Back the keystore up off this machine**: lose it and the published app
  can never be updated again, because Play matches the signing identity rather
  than the package name.
- **Play Console / App Store Connect** accounts.
- ~~**Biometric unlock** — mandatory or opt-in?~~ **Resolved: opt-in.** Built.
  Say so if you want it mandatory instead; the controller already holds the
  preference, so it is a policy change rather than a rewrite — but note a
  mandatory lock cannot be satisfied on a device with no credential enrolled.

---

### 1.4 The restored database has no column defaults — document upload is broken

Confirmed on 2026-08-18 against the local backend. **`sys.default_constraints`
holds exactly 1 row for 94 user tables**, and `nexora_platform_dump (1).sql`
contains the word `DEFAULT` **zero times**. The dump was generated without
column defaults, so every database restored from it is missing all of them.

The application was written against the module migrations, which *do* declare
them. `modules/document_extraction/sql/0001_document_extraction_tables.sql:67`
declares `import_guid UNIQUEIDENTIFIER NOT NULL DEFAULT NEWID()`; the live table
has the NOT NULL and not the default. `repository.create_import` supplies 9
columns and lets the schema fill 13 others (`import_guid`, the seven `is_*`
flags, `validation_status`, `uploaded_at`, `created_at`, `is_deleted`), so the
insert cannot succeed:

    IntegrityError: Cannot insert the value NULL into column 'import_guid',
    table 'nexora_platform.dbo.doc_import'; column does not allow nulls.

**Mobile document capture cannot work at all against such a database** — the
very first call of the pipeline 500s. This is almost certainly not confined to
document extraction; 94 tables are affected and the 152 `DEFAULT` clauses across
the 44 module migrations are all missing from the deployed schema.

`backend/scripts/restore_column_defaults.py` reads the declared defaults back
out of a migration file and emits the `ALTER TABLE` statements. It **prints and
stops** unless `--apply` is passed, since it changes a live schema and parses
hand-written SQL. For document extraction it produces 26 statements, verified
against the migration. Constraints are named `DF_<table>_<column>` so any of it
can be dropped again, and only columns currently missing a default are touched.

    backend/.venv/bin/python scripts/restore_column_defaults.py \
        modules/document_extraction/sql/0001_document_extraction_tables.sql

**Not applied** — the user declined the schema change on 2026-08-18. Until it is
applied (or the defaults are supplied explicitly in every INSERT), the Phase 2
exit criterion cannot run and neither can document capture.

## 2. What has been built

### Phase 0 — Architecture & Setup 🟡 partial

**Done**
- **OpenAPI snapshot is current again** — `routes.json` went from **43 paths to
  348**, i.e. it had been missing ~87% of the API including the entire mobile
  BFF. `backend/scripts/dump_openapi.py` regenerates it **with no server
  running** (`api.app` imports offline — its schema bootstraps are already
  wrapped in try/except), and `--check` fails if the file has drifted. Paths are
  sorted so a one-route change reads as a one-route diff, and it is now UTF-8;
  the old file was UTF-16 from a PowerShell redirect.
  Not wired into CI on purpose: importing the app pulls opencv, pymupdf,
  playwright and friends, which is a large install for a snapshot that only
  needs refreshing when routes change. Run it when they do.
- **Release signing is configured** — `android/app/build.gradle.kts` reads a
  keystore from `android/key.properties` (local, gitignored) *or*
  `AXYTHIC_KEYSTORE_*` environment variables (CI secrets); see
  `android/key.properties.example`. With neither it still falls back to debug
  keys so `flutter run --release` works, but `AXYTHIC_REQUIRE_RELEASE_SIGNING=true`
  turns that fallback into a build failure — set it on anything meant for
  distribution. Both paths verified: the fallback builds a 72.0MB universal
  APK with R8/resource shrinking enabled, the
  guarded path fails naming the missing keystore.
  The env-var route exists because `flutter build` does **not** forward `-P`
  Gradle properties, so a property alone would be unreachable from CI.
- **Release builds are HTTPS-only by construction.** The main manifest now
  explicitly sets `usesCleartextTraffic=false`; development exceptions live in
  `android/app/src/debug/` — a debug-only manifest and
  `res/xml/network_security_config.xml` — so a developer can still reach the
  plain-HTTP HO server while the release APK inherits the platform default and
  cannot. Verified against the merged manifests: `networkSecurityConfig` is
  present in the debug one and absent from the release one. The debug config
  also trusts user CAs, which is what lets a proxy like Charles inspect traffic.
- **A prod build pointed at `http://` now fails at `AppConfig.resolve()`** with
  a message naming the URL, rather than installing and then failing every
  request with an opaque transport error. `AppConfig.isCleartext` is exposed for
  diagnostics.
- `.github/workflows/mobile-ci.yml` — format gate, `analyze --fatal-infos`,
  tests, Android + iOS builds, integration tests on a booted simulator.
  Runs `build_runner` first: generated sources are gitignored, so without it the
  tree does not compile. The Android job **upgrades itself**: with
  `AXYTHIC_KEYSTORE_BASE64` set it decodes the keystore and builds a signed
  release with signing enforced; without it, it builds debug as before. The
  format gate now also covers `integration_test/`, which it previously skipped
  while the documented local command did not.
- `.github/workflows/backend-ci.yml` — three jobs:
  - `unit-tests` (`backend/tests`) — **blocking**
  - `legacy-tests` (root `tests/`) — **non-blocking** on purpose: 153 pass, 23
    fail, 1 collection error, all pre-existing. Flip `continue-on-error` off once
    green; do not delete the job to silence it.
  - `secret-scan` — gitleaks + a hard fail if any `.env` is ever tracked again.
- `backend/requirements-dev.txt` — minimal test deps (the full requirements pull
  paddlepaddle ~500MB that no test touches). Verified in a clean venv.
- **Repo-wide `dart format`** applied (42 of 117 files were non-compliant).

**Not done — all of it needs you, not code:** TLS on the HO server, an actual
release keystore to drop into the config above, Play Console / App Store Connect
accounts, Figma.

**iOS cleartext has no debug escape hatch, deliberately.** `Info.plist` is one
file across configurations, so a dev-only ATS exception would mean either a
second plist wired per-configuration in `project.pbxproj` or an exception that
ships. Neither is worth it for a workaround that TLS deletes: an ATS exception
for a hardcoded IP is also a routine App Review question. Until the HO server
serves HTTPS, iOS development against it needs a temporary local `Info.plist`
edit — do not commit one.

### Phase 1 — Foundation & Rebrand ✅

- **Axythic dark-only theme.** `app_colors.dart` now carries the real design-system
  dark tokens from `frontend/src/design-system/tokens/theme.ts` (the old palette
  used `#2547D0`, not an Axythic colour). `app_theme.dart` is one dark theme,
  ~20 component themes, `themeMode` pinned, system bars matched.
- **Five-tab shell** (`StatefulShellRoute.indexedStack`):
  `Home · Capture · Procure · Sync · More`. Each tab keeps its own back stack;
  re-tapping the active tab pops to root.
- **Capability gating** (`core/navigation/app_capability.dart`) — resolves
  `user.modules[]` by case-insensitive substring (server module codes are
  inconsistent: `PROCUREMENT_CYCLE_REFRESH`, `supplier_stock_analysis`).
  **An empty `modules[]` is permissive, not deny-all** — the backend returns that
  when no `role_module_access` rows are seeded, and deny-all would hand a
  successfully logged-in user an empty app.
- **Mobile BFF** — `backend/modules/mobile_bff/`, 6 endpoints, purely additive:
  `handshake · auth/login · auth/refresh · auth/logout · auth/devices · dashboard`
- **Session now survives past 12h** (was the failing exit criterion).
- **Dashboard aggregate** — one call replaces several on app open.
- **Launcher icons** — 20 generated from `axythic-mark.svg`, zero alpha.
- Bundle IDs `com.axythic.mobile` on both platforms; label/display name `Axythic`.

- **Unlock on open** — `core/security/`. **Opt-in, not mandatory**, which was
  the open question in §1.3: the Settings spec already lists biometrics as a
  setting, and a mandatory lock is unsatisfiable on a phone with nothing
  enrolled. Off by default, toggled from More → SESSION.
  The design decisions that matter, each of which is a way this feature bricks
  an app if it goes the other way:
  - **Device credential stays allowed** (`biometricOnly: false`). A cut finger
    or a failed sensor otherwise strands a user holding a valid session, whose
    only exit is a sign-out they may have no signal to undo.
  - **The lock screen always offers Sign out.** Same reason, one layer down.
  - **The preference stands down by itself** if the device credential
    disappears — at bootstrap and mid-session — rather than showing a prompt
    that cannot succeed.
  - **Enabling prompts before it persists**, so the toggle cannot arm a lock
    the device will not open.
  - **30-second grace period on resume** (`kAppLockGracePeriod`). Zero would
    re-prompt after every share sheet and photo picker, which is how a security
    feature gets switched off. `inactive` is ignored entirely (a notification
    shade is not leaving the app), and only the *first* background stamp counts
    — iOS emits hidden→paused on the way out, and restamping would push the
    deadline forward forever.
  - **Locking is not signing out.** The gate is a cover over the widget tree,
    installed via `MaterialApp.router`'s `builder` rather than as a route, so
    it also covers the camera on the root navigator and cannot be dismissed by
    a back gesture. Sync and the capture upload queue keep running behind it,
    which is the entire point of a queue that drains on reconnect.
  - **Android `MainActivity` now extends `FlutterFragmentActivity`.** `local_auth`
    shows AndroidX `BiometricPrompt`, a Fragment, which needs a FragmentActivity
    host; under the plain `FlutterActivity` it throws `no_fragment_activity` at
    the moment the user taps Unlock — clean build, clean analyze, clean unit
    tests, fails on a real device.
  - iOS needs `NSFaceIDUsageDescription`, now present. A missing string there is
    a **process kill**, not a denial.
  **20 tests.**
- **Offline banner** — `core/widgets/offline_banner.dart`, mounted once in
  `AppShell` above the branch content so every tab and every future screen gets
  it without remembering to. It states what still works ("your work is saved
  and will sync later") rather than only what is wrong, because in this app
  that is true and a bare "No connection" makes people stop working when they
  need not.
  `networkStatusProvider` **probes the current status before following the
  stream**: `ConnectivityService.statusStream` carries *transitions* only, so a
  widget watching it alone would show nothing on a phone that has been offline
  since launch — from its point of view nothing has happened. **5 tests.**
- **Local crash capture** — `core/observability/crash_reporter.dart`. This
  closes a real gap that existed regardless of any future remote reporting.
  **Nothing was catching uncaught errors at all.** All three doors are now
  covered — `FlutterError.onError` (framework), `PlatformDispatcher.onError`
  (uncaught async, which is most failures here) and a `runZonedGuarded` around
  the whole of bootstrap. The async handler returns `true` deliberately: `false`
  re-raises to the platform and ends the Android process, so one failed
  background upload would take the app down. The default implementation logs and
  keeps the **last 20 failures in memory** (RAM only — crash detail can contain
  invoice values), so a device can answer "what went wrong earlier?" without a
  server. A remote reporter can be added through the existing `CrashReporter`
  interface if the product chooses one in a future phase. **4 tests.**

### Phase 2 — OCR Document Extraction ✅ code-complete · exit criterion blocked on §1.4

**Done — data layer**
- Deps: `camera 0.11.4`, `image_picker 1.2.3`, `permission_handler 11.4.0`,
  `image 4.8.0`, `share_plus 10.1.4`, `open_filex 4.7.0`.
- Native permissions added **with** the feature (Play Console flags sensitive
  permissions declared ahead of use). `android.hardware.camera` is
  `required="false"` so a camera-less tablet can still review and export.
  iOS purpose strings state *why* — vague strings are a routine 5.1.1 rejection.
- **Drift schema v4** — `CaptureBatches` + `CapturePages` with migration.
- `capture_queue_repository.dart` — backoff 30s→2m→10m→30m, 6-attempt cap,
  `retryNow()`, disk hygiene (page images live outside the DB).
- `document_extraction_api.dart` — typed client for the whole pipeline.
- `capture_uploader.dart` — drains the queue, walks each import through
  preprocess → ocr → extract → validate.

**Done — camera capture**
- `capture_processor.dart` — **one** decode pass in an isolate produces both
  the upload JPEG and the quality verdict. Bakes EXIF orientation, caps the
  long edge at 2400px (~200 DPI on A4; 4-8 MB originals land at 500-900 KB).
- **On-device quality gate** (`capture_quality.dart` + the analyser in
  `capture_processor.dart`) — variance of the Laplacian for blur, clipped-pixel
  fraction for glare, mean luma for exposure, plus a resolution floor. Measured
  on a fixed 720px raster over the centre 80% (the region the viewfinder
  brackets mark) so metrics are comparable across devices. It **advises, never
  blocks**: a faded thermal invoice can score badly and still be the only copy
  that exists.
- `capture_storage.dart` — pages under `documents/captures/<session>/`, not a
  cache dir the OS may evict. `sweepEmptySessions()` reclaims directories
  orphaned by a crash between "write page" and "queue batch".
- `capture_session_controller.dart` — the in-progress multi-page document;
  add / retake / remove / reorder / commit / discard. Commit hands the files to
  the queue and starts a **new session id**, so a later discard cannot delete
  pages that are waiting to upload.
- `camera_capture_screen.dart` — full-screen viewfinder pushed onto the **root**
  navigator (`parentNavigatorKey`) so the tab bar is not under a camera.
  Letterboxed preview (never cropped — invisible content is content the user
  discovers is missing after the supplier has left), corner-bracket overlay,
  tap-to-focus + exposure metering, torch, thumbnail filmstrip, gallery import,
  resolution fallback ultraHigh → veryHigh → high, per-shot quality banner with
  Retake, and a confirm-before-discard guard.
- `capture_screen.dart` — the Capture tab is now a launcher: scan CTA, import,
  a resume card for a half-captured document, and queue counts.
- DI in `core/di/capture_providers.dart`; route `AppRoutes.cameraCapture`
  (`/capture/camera`).
- **37 new tests** (114 → 151): quality-gate verdicts against synthetic pages,
  session/queue hand-off and file ownership, and widget tests that actually
  render the surfaces.

**Done — the queue**
- `capture_queue_entry.dart` — pure, time-explicit mapping from a stored row to
  a stage, a sentence and a set of buttons. It is deliberately coarser than
  `DocumentStatus`: every server pipeline state reads as "working on it" to
  someone at a counter, while the two states the server knows nothing about —
  **backing off** and **given up** — are exactly the ones a user must act on.
- `capture_queue_screen.dart` + `capture_queue_card.dart` — a card per
  document with its thumbnail, why it is stuck, when it retries, and the one
  button that resolves it. Leads with whatever needs a person. Pull-to-refresh
  works on empty and error states too, since that is the only way back from a
  transient failure.
- `capture_queue_controller.dart` — retry / delete / reclaim semantics, out of
  the widget tree so they are testable. Two notes worth keeping:
  - **Delete hits the server first.** Dropping the local row and then failing
    would strand an import the user believes is gone and can no longer see. A
    server refusal leaves the local copy so the delete can be retried.
  - **Offline retry is not a failure.** `retryUpload` reports "still offline,
    it will upload when you reconnect" — calling that a failure trains users to
    keep tapping.
- `capture_sync_coordinator.dart` — **this is what makes offline capture
  actually work.** Drains on the connectivity stream returning online, and
  polls only documents the server is still working on (8s, timer stops when the
  queue is quiet). Started from `app.dart` when a session becomes ready.
- `CaptureUploader.retryPipeline` — re-runs the pipeline for an uploaded
  document that failed extraction, so a server-side failure never re-uploads
  pages the server already has.
- **32 more tests** (151 → 183).

**Done — review**
- `document_review_screen.dart` — the screen the capture flow exists to reach.
  Ordered by what a reviewer actually asks: is this trustworthy (findings and
  a totals reconciliation), is the header right, then the lines. Reached from
  `QueueAction.review` at `/capture/review/:importId?batch=<localBatchId>`.
- **The invoice is reconciled, not just validated.** The server's rules check
  that a field is present and parseable; `DocumentReview.reconciliation`
  checks the document against itself — net amount, total quantity and line
  count against what the included lines actually sum to. Ported from the web's
  `reviewChecks.ts` so both consoles call the same thing wrong, with one
  difference: a count that is one out is a mismatch, where money inside a
  rupee is rounding.
- **Findings land on the line they are about.** `ValidationFinding` now parses
  `rule_code` and `item_id`; header-level findings head the summary card and
  per-line ones render on that line's card.
- `review_item_card.dart` — a card per line, never a grid. Leads with what
  identifies the line, then batch/expiry/qty/rate/MRP, then why it is flagged
  (missing product, low confidence, invalid batch, invalid expiry — the web's
  four highlights). A **"Only flagged" filter** appears only when it would
  hide something.
- `review_edit_sheet.dart` — one sheet type for header, amounts, supplier and
  line edits. Sends **only changed fields**, because the server writes one
  audit row per changed field. A field left blank means "keep what is there":
  the server drops nulls from a patch, so a blank could never have cleared it.
- `document_page_view.dart` — the source image viewer, fetched **through Dio**
  so the bearer token goes with it (a bare `Image.network` renders a broken
  image and never says why). Zoomable, pageable, and switchable between the
  preprocessed image OCR actually read and the original photograph.
- **Exclusion is one-way** — the server has `exclude` and no un-exclude — so
  removing a line confirms first and says so. Excluded lines stay visible,
  dimmed and out of the totals.
- A **saved invoice is read-only**: the edit affordances disappear rather than
  letting someone change values that have already been committed.
- **55 new tests** (258 → 313), plus a second integration test file that runs
  the screen on a simulator — including a real PNG decoded on the device, so
  the viewer's image path is exercised outside the fake test codec.

**Done — export**
- `document_export_controller.dart` — `createExport` → `downloadExport` →
  share sheet, then `syncStatus(EXPORTED)` + `markExported` on the local rows
  so "Free up space" can reclaim their page images.
- **One workbook per export, covering every selected invoice**, which is what
  the frozen 5-sheet contract is shaped for — an accountant would rather have
  one file for the morning than seven. Two entry points: the review screen's
  bar once an invoice is saved (the moment someone actually wants to send it
  on), and **Export N saved invoices** in the queue's menu.
- **The file is renamed on the way out.** The server serves it as
  `<uuid>.xlsx`; a workbook landing in someone's chat under that name tells
  them nothing. It becomes `axythic-<invoice>-<date>.xlsx`, with the invoice
  number sanitised — real ones contain `/`.
- **`EXPORTED` was an unknown status to the client**, so it parsed as
  `UPLOADED`, i.e. "still working on it" — a document would have polled
  forever after its own export. Now a real enum value, a queue stage, and the
  point at which page images become reclaimable.
- The workbook itself is verified by `backend/tests/test_document_export.py`,
  which reads the expected sheets and columns **out of the frozen contract
  document** rather than retyping them, so drift on either side fails.
- **37 more tests** (298 → 335 mobile; 37 → 51 backend).

**Not done (the remaining Phase 2 work):**
- [ ] **Run the exit criterion end to end.** A harness now exists and the round
      trip was attempted for the first time on 2026-08-18. It reached step 3 of
      8 and stopped on a **backend bug, not a mobile one** — see §1.4. The
      harness is `backend/scripts/verify_extraction_roundtrip.py`: it mirrors
      `CaptureUploader.pipeline` and `DocumentExtractionApi` call for call,
      generates a legible 200-DPI test invoice, and verifies the exported
      workbook against the sheets and columns parsed **out of the frozen
      contract document**. Its offline halves are verified — the contract parser
      reads all 5 sheets, and the generated invoice renders correctly.
      Note also that **the HO host is the unreachable one**: a full backend runs
      on `localhost:8000` with the complete extraction pipeline, so this is
      runnable the moment §1.4 is resolved.
- [ ] **Calibrate the quality thresholds against real store captures.** They
      are currently tuned on synthetic pages and printed-invoice assumptions
      (`_sharpnessReject` and friends in `capture_processor.dart`). Leaning
      lenient is deliberate: a false "retake" on a good page teaches users to
      ignore the gate.

### Phase 3 — Core Operations ✅ (workmanager tick skipped on judgment)

Started ahead of finishing Phase 2, at the user's explicit direction.

**Done**
- **Sync Live** — `sync_live_service.dart` + `sync_live_screen.dart`. Per-store
  live progress over `GET /api/sync/live`, pause/stop via `POST /api/sync/control`,
  and a history sheet over `GET /api/sync/history`. Polls every 5s **only while
  the screen is watched** (`autoDispose` owns the timer), so a backgrounded tab
  is not hitting HO. Online-only by design — nothing is cached, because a stale
  answer to "is store 7 syncing?" is worse than no answer.
- **Reports** — genuinely catalog-driven. `GET /api/reports` publishes each
  report *and which inputs it needs*, so the filter sheet and the result grid
  are both generated: **a report added on the server appears without an app
  release.** Rows render as cards, not a 16-column grid nobody can read on a
  phone. Share exports CSV via `share_plus`.
- **Supplier** — the list/detail UI, which was the actual gap: the data layer
  (Drift cache, delta sync, repository) already existed. Reads **only** the
  local cache so search works with no signal; pull-to-refresh asks the sync
  engine to run rather than fetching directly, keeping one path responsible.

- **Offline outbox** — `core/outbox/` plus Drift **schema v5** (`OutboxEntries`).
  Review edits no longer die when there is no signal: a network failure queues
  the change and reports it as saved, because from the user's side it is.
  The decisions that carry the weight:
  - **Only a network failure is queued.** A server that *refused* an edit will
    refuse it again in an hour, so queueing a rejection would convert a clear
    error into a change the user believes is on its way and that quietly
    dead-letters later.
  - **Strict per-scope ordering.** `due()` returns at most one entry per scope
    (`import:42`), so two edits of one document can never be sent concurrently
    or out of order. A backed-off entry blocks its own scope and nothing else;
    a dead-lettered one steps aside so it cannot strand every later change.
  - **An offline retry does not burn an attempt.** Otherwise a tunnel marches a
    perfectly good edit toward the dead-letter list.
  - **Interrupted entries are recovered at start.** The app can be killed
    between "mark in flight" and the response; those rows would otherwise sit
    in `inFlight` forever, never sent and never reported as stuck.
  - **An unknown kind dead-letters immediately** rather than retrying — it means
    an older build queued something this one cannot send, and waiting cannot fix
    that. Kinds are string constants precisely because they are persisted;
    renaming an enum value would orphan a queued edit.
  - **Queued edits re-run validation when they land**, for the same reason
    online ones do (§3.12).
  - **A concurrency bug was caught by its own test**: `drain()` set its
    re-entrancy guard *after* awaiting the connectivity check, so two callers
    both passed the guard and the same edit was sent twice. The guard is now
    claimed synchronously before the first await.
  - Three triggers — on start, on reconnect, and a 5-minute sweep that stops
    when the outbox empties (a server that was down while the device was online
    the whole time produces no connectivity event).
  **36 tests.**
- **Settings** — `settings_screen.dart` + `pending_changes_screen.dart`.
  Security, server, storage, diagnostics and pending changes in one place, and
  Device/Configuration/Agent Settings moved off More into it. That was the
  actual fix for "Sign out is below the fold": the integration test now asserts
  Sign out's rect is on screen without scrolling.
  **No theme control** — the product is dark-only by decision, and a switch that
  does nothing is worse than its absence because it invites a bug report.
  **No WhatsApp section** — nothing in the mobile app touches WhatsApp, so there
  is nothing to configure; the plan's mention refers to the web console.
  Pending changes is the surface that makes the outbox honest: what is waiting,
  what needs a person, retry, and a discard that names the loss. **11 tests.**

- **Report results are cached and read offline** — Drift **schema v6**
  (`ReportCacheEntries`) plus `reports_repository.dart`. The runner screen now
  goes through the repository rather than the API directly.
  - **Network-first, not cache-first.** A report is a question about *now*, so a
    fresh answer always wins; the cache exists for the manager standing in a
    stockroom with no signal, not to save a round trip.
  - **Only a network failure falls back.** A 401 or a rejected filter is a real
    answer, and replacing it with yesterday's numbers would hide the actual
    problem.
  - **Staleness is always visible** — a banner naming the age ("Saved figures
    from 3 hours ago"), because the reader's real question is not "is there
    signal" but "how old are these numbers".
  - **Two days maximum.** A week-old stock figure is not an answer to "what do
    we have", and showing one invites someone to act on it.
  - The cache key includes tenant, store and only the filters the report
    *declares*, so a store switch can never surface the previous store's
    numbers and a stale supplier selection cannot split the cache for a report
    that never sends it. `ReportFormat.int_` round-trips as the wire spelling
    `int` — the Dart name exists only because `int` is reserved.
  **37 tests.**
- **The outbox also drains on app resume** (`AppLockGate`). A phone that was
  offline in a pocket and is now on the shop wi-fi produces no connectivity
  event — the OS reconnected while the app was suspended — so without this the
  user waits out the five-minute sweep.

**Not done — and a judgment call worth reading before reversing it**
- [ ] **`workmanager` background tick.** Deliberately not shipped. It would run
      in its own isolate, which cannot share the Riverpod graph *or the open
      Drift connection* — a second SQLite connection to the same file from
      another isolate is how databases get corrupted, and that risk lands on
      users' devices. It also cannot be verified here: iOS `BGTaskScheduler` is
      opportunistic, needs a capability entitlement, and a simulator does not
      run background tasks.
      What it would add over what now exists — drain on start, on reconnect, on
      resume, and every five minutes while open — is sending edits while the app
      is fully closed. For staff using the app actively on a shop floor that is
      a small gain for a real hazard. If it is wanted, do it with Drift's
      documented cross-isolate setup (`DriftIsolate`), not a second
      `openDatabaseConnection()`, and verify on physical hardware.
- [x] ~~Supplier BFF endpoint~~ — **done.** `GET /api/mobile/v1/suppliers`
      serves the same query and the same `{suppliers: [...]}` payload with
      scope resolved from the JWT instead of a role gate, so purchase-manager
      and salesman logins finally get a supplier list. Deliberately narrow:
      supplier products, stock, matching, reports and the cross-store
      dashboards stay behind `require_admin_role`. The mobile sync now points
      at it and no longer sends `tenant_id` at all.

### Phase 4 — Procurement & Admin ✅ 4 of 4 modules done

Started at the user's explicit direction, with Phases 2 and 3 both incomplete.

**Done**
- **Pass Gen** — `pass_gen/`. Mints the legacy 14-character store passcodes.
  Platform-admin only; the More tile is hidden for everyone else because the
  endpoint 403s them and offering a dead end is worse than hiding the feature.
  Ships the **single-row** subset of the desktop batch tool — the wire format
  still carries a rows array, so batching needs no server change. Unmapped
  stores are named in a "skipped" card and can be given a numeric code inline,
  which is the difference between "seven of ten codes" being explicable or
  looking broken.
- **Time Report** — `time_report/`. Four of the five report kinds: daily
  (department-grouped), miss punch, user (summary/detail), inactive. Export
  fetches the **server-built** xlsx rather than rebuilding it on device, so the
  styling matches the desktop export the same team reads. A 503 is surfaced as
  "the attendance system is not reachable", because COSEC is separate
  infrastructure and a generic error sends the support call to the wrong team.
- **26 new tests** (232 → 258).

- **Cycle & Refresh Console** — `procurement/` (`cycle_models.dart`,
  `cycle_api.dart`, `cycle_providers.dart`, `cycle_console_screen.dart`), live
  from the Procure tab.
  **Scoped deliberately** to the three actions that block other people — see
  where the cycle is, start the next refresh, close a refresh or a cycle. The
  desktop console also edits order items line by line, which does not survive
  phone width and is not what someone away from a desk needs.
  The details that matter:
  - **Field names were read off a live response**, not inferred from the
    router. The row carries `cycle_id`, `active_refresh_id` and *nullable* end
    counters; `active_refresh_id` is what decides whether the card offers
    "Start refresh" or "Close refresh".
  - **Unstamped counters render as "Not stamped", never 0.** These are counter
    readings — a zero reads as a real one.
  - **`pending_confirm` is a question, not a failure.** `close_cycle` returns it
    when items remain and `force` was not set. The console puts that back to the
    user naming the count, and only then retries with `force` — closing over
    unresolved items is a decision, not a retry. `CloseOutcome` exists precisely
    so this cannot be mistaken for an error.
  - **An unrecognised status is shown as the server's own word**, not collapsed
    to "Unknown" — a state this build has not heard of is information.
  - **Starting a refresh warns that it is slow.** The server runs the engine and
    generates working items before responding; a user who thinks the app has
    frozen kills it mid-run.
  - §3.8 again: the action buttons live in a `Wrap`, which has the same
    unbounded-main-axis problem as a `Row`, so each carries an explicit
    `minimumSize`.
  **13 tests.**
  **Push-on-completion is deferred to a future phase.** Nothing else in the
  console is pending.

- **Legacy Order Console** — `procurement/` (`legacy_order_models.dart`,
  `legacy_order_api.dart`, `legacy_order_providers.dart`,
  `legacy_order_console_screen.dart`), live from the Procure tab for platform
  and super-admin users only, matching the router's own gate.
  - **Read-only OrderNMC health** remains visible even when `/stores` is 503,
    so an outage explains itself. Database recovery and emergency repair are
    deliberately not exposed on a field phone.
  - Store cards show branch connection metadata and the last sync result.
    Sync, Order Process and Stock Update use the existing server jobs; running
    jobs poll every two seconds only while one is active and keep their recent
    log visible.
  - Order Process carries the server's 13/18 defaults and local/remote modes.
    NMW cannot run Stock Update against itself because it is the source store.
  - Qty Check is a card list rather than the desktop's 13-column grid. Review
    accepts zero as the legacy “Don't want to order” decision, and Evidence
    loads purchase, sales, monthly and previous-order history from the four
    documented drill-down endpoints.
  - The first rendered 390px test caught a 7px overflow in the local/remote
    source control; it now wraps. **15 tests.**

**Not done**
- [ ] **Time Report's monthly muster grid.** Deliberately skipped: it is a
      day-by-day colour matrix per user, which does not survive phone width.
      The xlsx export covers the mobile need; the grid stays on desktop.
- [ ] Time Report's PNG / zip image endpoints (`/daily/image`, `/daily/images`).

**Watch out:** Time Report is the one module where **column specs live on the
client** (`TimeReportColumns`). Unlike `/api/reports`, this API publishes no
column metadata — the server's own comment says the frontend renders each shape
with a dedicated view. A column renamed in `time_report/service.py` will show
as a missing field here with no error.

---

## 3. Non-obvious implementation details

Things that will be re-broken if someone does not know them.

### 3.1 Refresh tokens are single-use — do not parallelise

The server treats a replayed refresh token as theft and **revokes the entire
device chain**. `TokenRefresher` therefore **single-flights**: concurrent callers
await one shared future. Two parallel 401s would otherwise fire two refreshes,
the second would look like a replay, and the user would be signed out *because*
the app tried to keep them signed in. There is a test asserting three
simultaneous calls produce exactly one HTTP request.

### 3.2 A 5xx on refresh must NOT end the session

`RefreshOutcome` distinguishes `rejected` (401 → session over) from `transient`
(5xx/timeout → **keep the session**). Signing users out because the HO server
hiccupped is worse than the expired token they started with.

### 3.3 `dart format` vs `require_trailing_commas`

They contradict each other; with both enabled `dart format` and
`flutter analyze` **cannot pass simultaneously**. The lint is disabled in
`analysis_options.yaml` with a comment. `dart format` is the single authority.

### 3.4 Drift singularisation

`CaptureBatches` would generate row class `CaptureBatche`. Fixed with
`@DataClassName('CaptureBatch')`. Apply the same to any new plural table.

### 3.5 `reprocess` uses noun forms

Trigger endpoints use verbs (`extract`); `reprocess`'s `from_stage` uses nouns
(`extraction`). `DocumentStage` carries both — see `path` vs `reprocessName`.

### 3.6 Defensive parsing is deliberate

OCR returns numbers as strings and rows with missing fields. A strict parse
would blank data the user must then retype. An **unknown pipeline status is
treated as in-flight, not terminal**, so a server ahead of the app keeps polling
rather than showing a wrong final state.

### 3.7 Cross-tab navigation uses `go`, not `push`

Device/Configuration/Agent screens live in the **More** branch. Navigating from
Home must `context.go(...)`, or they stack onto Home and the tab bar desyncs.

### 3.8 A themed button cannot be a direct child of a Row

`app_theme.dart` gives filled and outlined buttons
`minimumSize: Size.fromHeight(52)` — and `Size.fromHeight` is
`Size(double.infinity, 52)`. A `Row` measures its inflexible children with an
**unbounded** main axis, so a themed `FilledButton` dropped straight into a Row
asserts *"BoxConstraints forces an infinite width"* at layout time. Give any
button inside a Row a real `minimumSize` (or wrap it in `Expanded`).

Found by rendering `_ResumeCard`; `analyze` passes it happily. The theme itself
was left alone on purpose — full-width-by-default is what every existing screen
relies on.

### 3.9 An indeterminate progress bar makes `pumpAndSettle` hang forever

The queue's processing card carries an indeterminate `LinearProgressIndicator`,
which by design never stops animating — so `pumpAndSettle` times out rather
than failing with anything that names the cause. Use `tester.pump()` twice in
any test whose surface can show a processing card.

Related: `ListView.builder` only builds what fits, so a test asserting that
*every* state renders needs a tall `tester.view.physicalSize`, not just a pump.
Both are in `capture_queue_screen_test.dart`.

### 3.10 `permission_handler` needs its iOS macros or the App Store rejects it

Left alone, the pod compiles **every** permission handler — contacts, location,
microphone, health — and review scans the binary for privacy-sensitive API
usage, rejecting anything without a matching Info.plist purpose string.
`ios/Podfile`'s `post_install` now sets `PERMISSION_CAMERA=1` and nothing else;
everything unlisted is compiled out. **Adding any new `Permission.x` call means
adding its macro there too**, or it silently returns denied at runtime.

### 3.11 `testWidgets` runs in fake async — do not await real I/O in one

The body of a `testWidgets` runs inside a `FakeAsync` zone. Awaiting a real
file read, or a Drift query, from the test body **deadlocks the whole test
file**: `flutter_tester` sits at 0% CPU and prints nothing at all, which looks
exactly like a hung compile. Feed screens plain data through provider
overrides (`capture_screens_test.dart` does this), or wrap real work in
`tester.runAsync`.

### 3.11a A Drift `watch()` stream never settles under `testWidgets` either

Same root cause as §3.11 and a separate trap. Feeding a widget from a live
Drift query — `outboxOutstandingProvider`, `captureQueueStreamProvider` — means
the stream needs real event-loop turns to deliver, which a fake-async body never
grants. The file times out with **no output at all**, exactly like a hung
compile, and `tester.runAsync` around the *seeding* does not fix it because the
problem is the watch, not the write.

Override the provider with plain rows instead:

```dart
outboxOutstandingProvider.overrideWith((ref) => Stream.value(rows))
```

`test/features/settings/settings_screens_test.dart` does this and runs in four
seconds; the version that used a real database hung past seven minutes twice.
Row classes are constructible directly (`OutboxEntry(...)`), so no database is
needed to build a realistic fixture.

### 3.12 An edit must re-run validation, or the fix does not count

`service.save` reads the **stored** `doc_import.validation_status`, and that
column only changes when `POST /imports/{id}/validate` runs. Nothing about
`patch_header` / `patch_item` / `exclude` / `supplier` recomputes it. So
correcting the missing invoice number the findings complained about leaves the
import still marked `FAILED`, and the user is asked to override an error they
have just fixed.

`DocumentReviewController._edit` therefore runs `validate` after every
successful edit, then reloads. It is cheap — `run_validation` is deliberately
stateless and re-derives from the rows — and a re-check that fails does **not**
fail the edit: the correction is already on the server, only the findings are
one edit stale. (The web console does not do this; it has the same trap.)

### 3.13 Finding severity is ERROR/WARNING, not the import's PASSED/WARNING/FAILED

`json_contracts.ValidationSeverity` is `ERROR | WARNING`, while
`doc_import.validation_status` is `PASSED | WARNING | FAILED`. Both land in
`ValidationStatus.fromWire`, so `ERROR` is aliased to `failed` there — without
it, every blocking finding silently parsed as `pending` and rendered as a
neutral badge.

### 3.14 Saving is the only thing that moves a document off "Ready to review"

`CaptureSyncCoordinator` polls only documents the server is still *working on*
(`status.isProcessing`), and `REVIEW_PENDING` is not one of them. So a save has
to mirror `SAVED` onto the local queue row itself — hence `batchId` riding
along in the review route's query string. Without it the user returns to a
queue still insisting they have work to do.

### 3.15 `EXPORTED` is a status the client has to know about

`service.export` sets `status = EXPORTED` on **every** import in the batch, so
it comes back from the server whether or not the export started on this device.
Before it was a real enum value, `DocumentStatus.fromWire` fell back to
`UPLOADED` — which `isProcessing` reports as true — so a document would have
been polled forever after its own export, and the queue would have shown it as
still being worked on. Any new server status needs the same treatment; the
fallback is deliberately in-flight, which is safe for a *new* stage and wrong
for a terminal one.

### 3.15a A re-entrancy guard must be claimed before the first `await`

`OutboxDispatcher.drain()` originally checked `_draining`, then awaited a
connectivity probe, then set the flag. Two callers — a reconnect event and a
manual retry arriving together — both passed the check, both suspended on the
probe, and both proceeded. The same edit was sent twice, which for this API
means **two audit rows for one correction**.

The guard is now set synchronously immediately after the check, and the
connectivity probe moved inside the `try` so the flag is still released. There
is a test asserting two concurrent drains produce one send. The same shape
exists in `TokenRefresher` (§3.1) and `CaptureUploader._draining` — check any
new one against this.

### 3.16 Bar index ≠ branch index

The shell always has all 5 branches; only the bar is filtered by capability.
With Capture and Procure hidden, Sync sits at bar position 1 but is branch 3.
`AppShell` maps between them and clamps a hidden active branch to 0 (otherwise
`NavigationBar` asserts).

---

## 4. Bugs found and fixed (do not reintroduce)

| Bug | Where | Fix |
|---|---|---|
| **`INTERNET` only in debug/profile manifests** — every release build would ship with no network permission and fail on the first API call | `android/app/src/main/AndroidManifest.xml` | Declared in the main manifest |
| **`StatusCard` crashed at runtime** — "A borderRadius can only be given on borders with uniform colors". Pre-existing; `analyze` and widget tests both passed it. Only found by *running* the app | `core/widgets/mobile_components.dart` | Accent drawn as a child stripe inside a `ClipRRect`, not a `BorderSide` |
| iOS app icon had a white box | icon generation | `qlmanage` renders SVG onto white; re-rendered via headless Chrome with a transparent background |
| **"BoxConstraints forces an infinite width"** — a themed `FilledButton` as a direct child of a `Row`. `analyze` passes it; only a paint pass catches it. See §3.8 | `document_extraction/presentation/capture_screen.dart` | Explicit `minimumSize` on any button inside a Row |
| **Save fell below the fold on a nine-field edit sheet** — with the whole form in one scroll view, a line edit put Cancel/Save ~50px past the bottom of the display. Found by the hit-test warning in the simulator run; every widget test passed | `document_extraction/presentation/widgets/review_edit_sheet.dart` | Fields scroll inside a `Flexible`; the actions are pinned. Regression test asserts Save's rect is on a 390×844 screen |
| **A line count rendered as money** — "Line count 3.00". Found by *looking at* the screenshot; every assertion passed | `document_extraction/presentation/widgets/review_summary_card.dart` | `ReconcileCheck.money` distinguishes amounts from counts |

| **The same edit sent twice** — `OutboxDispatcher.drain()` claimed its re-entrancy guard *after* awaiting a connectivity probe, so a reconnect event and a manual retry both got through. For this API that means two audit rows for one correction. See §3.15a | `core/outbox/outbox_dispatcher.dart` | Guard claimed synchronously before the first await; test asserts two concurrent drains produce one send |
| **A queue that loses its images across an iOS reinstall** — `CapturePages.filePath` held an absolute path, and the app container UUID is reassigned on reinstall | `document_extraction/data/capture_queue_repository.dart` | Paths stored relative to the captures directory and resolved on read. Legacy absolute rows still resolve, so nothing is orphaned |
| **The offline banner would never appear on a cold start that was already offline** — `ConnectivityService.statusStream` carries *transitions*, and from a widget's point of view nothing had happened | `core/di/providers.dart` | `networkStatusProvider` probes the current status, then follows the stream |
| **Document upload 500s against any database restored from the dump** — 13 columns rely on schema defaults the dump did not carry. Backend, not mobile; see §1.4 | `nexora_platform_dump (1).sql` | Not applied — `backend/scripts/restore_column_defaults.py` is ready and awaiting a decision |

**Lesson worth keeping:** static analysis and widget tests passed the
`StatusCard` crash straight through. Run the app on a simulator as part of
verification — and make sure the widget tests actually *render* the widget,
which is what caught the infinite-width bug above. Both review bugs above
followed the same pattern: green tests, wrong on a phone. A screenshot is part
of verification, not a nicety.

---

## 5. Current state

- **Branch:** `bharath-develop`
- **Last commit:** `8fe5fd2` — everything up to and including the first
  document-extraction/sync/dashboard push. The security fix `b192104` is behind
  it.
- **Uncommitted: 38 modified + 27 untracked.** All of the Phase 0–4 work
  described in §2 lives in the working tree and nowhere else.

⚠️ **This is the single biggest continuity risk.** Several sessions of work sit
in one uncommitted tree with no branch protecting it. §7 says do not commit
without being asked, so it has been left alone deliberately — but *ask*, early.
`git add -A && git commit` beats losing it.

New this session (Phases 0–4), on top of what was already there:

| Area | Where |
|---|---|
| Unlock on open | `core/security/` |
| Crash capture | `core/observability/crash_reporter.dart` |
| Offline banner | `core/widgets/offline_banner.dart` |
| Offline outbox | `core/outbox/`, `core/database/outbox_tables.dart` |
| Settings + pending changes | `features/settings/presentation/` |
| Report cache | `core/database/report_cache_tables.dart`, `features/reports/data/reports_repository.dart` |
| Cycle & Refresh Console | `features/procurement/` |
| Legacy Order Console | `features/procurement/` |
| Backend scripts | `backend/scripts/dump_openapi.py`, `restore_column_defaults.py`, `verify_extraction_roundtrip.py` |

**Drift schema is now v6.** v5 added `OutboxEntries`, v6 added
`ReportCacheEntries`. Both have `onUpgrade` steps; do not renumber them.

### Verification commands (all currently green)

```bash
cd mobile
dart run build_runner build --delete-conflicting-outputs
dart format --output=none --set-exit-if-changed lib test integration_test  # exit 0
flutter analyze --fatal-infos                                              # No issues found
flutter test                                                               # 470 passed
flutter test integration_test -d <simulator-udid>                          # 6 passed
dart run tool/verify_release_readiness.dart                                # 8 files passed
flutter build apk --release --dart-define=NEXORA_ENV=prod \
  --dart-define=NEXORA_API_BASE_URL=https://example.invalid                # 72.0MB universal APK, R8 enabled, debug-signed
flutter build ios --release --no-codesign --dart-define=NEXORA_ENV=prod \
  --dart-define=NEXORA_API_BASE_URL=https://example.invalid                # 25.1MB Runner.app

cd ../backend
.venv/bin/python -m pytest tests/ -q                                       # 61 passed
.venv/bin/python scripts/dump_openapi.py --check                           # routes.json is current
```

Run the app against the **HO** backend:

```bash
flutter run --dart-define=NEXORA_API_BASE_URL=http://122.252.246.181:8443
```

A simulator must be fully booted before `flutter test integration_test` — a
`Shutdown` device fails at install with a misleading "malformed plist" error.
`xcrun simctl boot <udid>` then `xcrun simctl bootstatus <udid> -b`.

### Suggested commit split

The first twelve are the pre-existing work; 13 onward is this session.

1. `feat(mobile): Axythic dark-only theme and native identity`
2. `ci: add mobile and backend workflows; normalise dart formatting`
3. `feat(mobile): five-tab navigation shell with capability gating`
4. `feat(api): mobile BFF with refresh tokens, logout and dashboard aggregate`
5. `feat(mobile): document capture queue and OCR pipeline client`
6. `feat(mobile): multi-page camera capture with on-device quality gate`
7. `feat(mobile): capture queue screen and reconnect drain`
8. `feat(mobile): sync live operations, reports runner and supplier master`
9. `feat(mobile): pass gen and time report`
10. `feat(mobile): invoice review, correction and authenticated page viewer`
11. `feat(mobile): workbook export and share from review and the queue`
12. `feat(api): mobile supplier endpoint for field roles the admin gate blocks`
13. `build(android): real release signing config, HTTPS-only release builds`
14. `chore(backend): regenerate routes.json from the app (43 → 348 paths)`
15. `feat(mobile): opt-in unlock on open with device-credential fallback`
16. `feat(mobile): global crash capture and an offline state banner`
17. `fix(mobile): store capture page paths relative to the documents directory`
18. `feat(mobile): offline outbox for review edits made without signal`
19. `feat(mobile): settings screen and a pending-changes surface`
20. `feat(mobile): cache report results for offline reading`
21. `feat(mobile): cycle and refresh console`
22. `chore(backend): scripts to verify the extraction round trip and restore column defaults`
23. `feat(mobile): legacy order operations and quantity-check console`
24. `build(mobile): start Phase 6 release hardening and store readiness`

---

## 6. Next steps, in order

The short list is in **▶ RESUME HERE** at the top. Everything still open,
grouped by phase:

**Blocked on the user, not on code**
1. **§1.4 — apply the missing column defaults.** One `--apply` unblocks Phase 2
   entirely. Declined once (2026-08-18); re-raise it, because until then
   document capture cannot work against this database at all.
2. **§1.1 — rotate the leaked JWT secret.** Highest severity item in this file.
3. **§1.2 — TLS**, **§1.3 — keystore and store accounts.**

**Phase 2 — one thing left, and it is the item above**
4. **Run the exit criterion.** The harness exists and is scripted:
   `backend/scripts/verify_extraction_roundtrip.py`. It got to step 3 of 8 and
   stopped on §1.4. Nothing about the mobile side is known to be wrong.

**Phase 4 — complete**
5. Push-on-completion is explicitly deferred to a future phase; it is not a
   current release requirement.

**Phase 5 — complete**
6. Purchase Workspace (reduced field scope), Refresh Compare, Stock
   Distribution monitor and conflict-resolution UI are implemented. Purchase
   quantity, assignment, skip and restore mutations use ordered procurement
   outbox kinds, and rejected mutations can be resolved against the latest
   server quantities. Verified with 467 unit/widget tests plus the iOS app-shell
   integration smoke test.

**Phase 6 — in progress**
7. **Done in the first release-hardening slice:** Android R8/resource shrinking;
   backups and cleartext disabled in the merged release manifest; iOS protected
   data entitlement and export-compliance declaration; semantic labels and tap
   target tests for shared status, metric and action components; store listing,
   privacy inventory and staged-rollout checklists; and a deterministic release
   readiness check in mobile CI. A minified Android release APK and unsigned iOS
   release app both compile successfully. All 470 unit/widget tests pass.
8. **Still pending:** profile startup, scrolling, memory and capture processing
   on representative Android/iOS hardware; audit every screen with TalkBack and
   VoiceOver plus large text; exercise camera, biometrics, secure storage, file
   opening/sharing and offline sync in a minified build; supply a real HTTPS
   production URL, signing credentials, privacy-policy/support URLs, final copy
   and screenshots; upload to internal testing/TestFlight; then execute and
   monitor the staged rollout. The universal APK is 72.0MB, so use Play's AAB
   delivery and capture download-size reports during internal testing before
   deciding whether further asset/native-library reduction is warranted.

**Cross-cutting, do whenever the relevant code is next touched**

- **Calibrate the capture quality thresholds** on real store captures
  (`_sharpnessReject` and friends in `capture_processor.dart`). Still the one
  Phase 2 item no amount of local work can substitute for.
- **The outbox has no UI entry point from the review screen.** A user who makes
  an offline correction is told it will sync, but only Settings → Pending
  changes shows it afterwards. A per-document indicator on the review screen
  would close that loop; `OutboxRepository.forScope('import:<id>')` already
  returns exactly that list.
- **`ReportsRepository.clear()` is written but never called.** It exists so a
  store switch cannot surface the previous store's numbers. The cache key
  includes the store id so this is not a correctness hole today, but wiring it
  to `AuthController.clearStore` would stop the cache growing per store.

### What the camera work has NOT been verified against

The iOS simulator has no camera, so `availableCameras()` returns empty there and
the screen renders its "no camera available" fallback. Everything downstream of
an actual shutter press is therefore **unverified on hardware**: preview
framing and rotation, tap-to-focus, torch, the resolution fallback chain, and
how the quality gate scores a real invoice under real store lighting. The
integration test covers the Capture launcher against the real Drift queue and
documents directory; it deliberately does not enter the camera, because
requesting the camera permission raises a system dialog that would hang CI.

First run on a real phone should check, in order: the preview is upright in
portrait, a shot lands in the filmstrip in under ~2s, and a deliberately
blurred page is actually flagged.

### Phase 2 exit criterion

> Photograph a real supplier invoice **offline**, reconnect, review, export a
> valid 5-sheet workbook, and open it in Excel — verified against
> `docs/Document_Extraction_Excel_Contract.md`.

---

## 7. Working agreements observed this session

- Verify by **running**, not just analysing — the `StatusCard` crash proves why,
  and every session since has found something the same way.
- Never invent an endpoint; read the router — or better, read a live response.
  The Cycle Console's model was shaped from real JSON off `localhost:8000`, and
  it carried nullable fields the router signature did not reveal.
  **`routes.json` is now current** (348 paths) and regenerable, so it can be
  trusted again — but it is a snapshot, so regenerate it rather than assuming.
- Report status honestly, including percentages and what is *not* done. If a
  thing is skipped on judgment rather than blocked, say which and why.
- Comments explain **why**, not what.
- **Do not commit without being asked.**
- Ask before writing to the user's database or changing its schema. Both came
  up this session; the record write was approved, the schema change was not.
