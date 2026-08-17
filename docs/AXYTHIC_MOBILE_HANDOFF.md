# Axythic Mobile — Session Handoff

**Read this first when resuming work on the Axythic mobile app.**
Last updated: 2026-08-16 · Branch: `bharath-develop`

Full implementation plan: `~/.claude/plans/hiii-bro-atomic-pillow.md`

---

## ▶ RESUME HERE

**Everything below is current as of the end of the last session. Nothing is
committed — all the work lives in the working tree.**

### 60-second orientation

This is **not a web app** — it is a Flutter mobile client (`mobile/`) plus a
FastAPI backend (`backend/`) that already serves a React web console. Mobile is
a *client* for existing server modules; the only backend code added so far is
the additive `backend/modules/mobile_bff/`.

Phases are **not sequential in practice**. Work was pushed forward at the
user's direction while earlier phases were still open, so there are unfinished
pieces in Phases 2, 3 and 4 at the same time. That is deliberate, not drift.

| Phase | State |
|---|---|
| 0 Setup | 🟡 CI done · **TLS / keystore / store accounts NOT done** |
| 1 Foundation | ✅ ~90% (no biometrics, no Crashlytics) |
| 2 OCR Capture | ✅ capture · queue · review · **export** — feature-complete; exit criterion needs a reachable server |
| 3 Core Ops | 🟡 Sync Live, Reports, Supplier (+ **BFF endpoint**) done · **Settings + outbox missing** |
| 4 Procurement | 🟡 Pass Gen, Time Report done · **Cycle Console + Legacy Order missing** |
| 5, 6 | ⬜ not started |

### First commands to run in a new session

```bash
cd mobile
dart run build_runner build --delete-conflicting-outputs   # generated sources are gitignored
flutter analyze --fatal-infos                              # expect: No issues found
flutter test                                               # expect: 335 passed
```

If `build_runner` is skipped the tree will not compile — `*.g.dart` and
`*.freezed.dart` are not in git.

### The three things that will bite you

1. **A themed button cannot be a direct child of a Row or Wrap** — §3.8. It
   asserts at *paint* time and `analyze` passes it. This has been hit twice.
2. **`testWidgets` runs in fake async** — §3.11. Awaiting real file/Drift I/O
   in a test body deadlocks the whole file with zero output at 0% CPU, which
   looks exactly like a hung compile.
3. **Verify by running, not analysing.** Every session so far, the integration
   test on a simulator caught something `analyze` and unit tests passed
   straight through. Run it.

### Highest-value next steps, in order

1. **Offline outbox + background sync.** The largest remaining MVP piece, and
   Phase 5's Purchase Workspace depends on it. It is also what would let a
   review correction be made offline — today edits go straight to the server
   and simply report the failure when there is no signal.
2. **Settings.** Server, theme, biometrics, cache, WhatsApp, diagnostics. The
   More tab is already long enough that this wants grouping, not appending.
3. **Run the Phase 2 exit criterion against a real server.** Everything in the
   path is built and tested, but the HO server is unreachable from a dev
   machine, so "photograph offline → reconnect → review → export → open in
   Excel" has never been run end to end. The workbook builder is now covered by
   a contract test (`backend/tests/test_document_export.py`), so what remains
   unverified is the round trip, not the file format.

**Nothing ships until TLS is up (§1.2), regardless of which of these is done.**

### Suggested opening message for the next chat

> Read docs/AXYTHIC_MOBILE_HANDOFF.md and continue. Start with <the item you
> want> from the "Highest-value next steps" list.

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

### 1.3 Blocked on user input

- **Release keystore** — Android still signs with debug keys
  (`mobile/android/app/build.gradle.kts`). Needs a real keystore in CI secrets.
- **Play Console / App Store Connect** accounts.
- **Crashlytics** — needs a Firebase project.
- **Biometric unlock** — needs a decision: mandatory on launch, or opt-in?

---

## 2. What has been built

### Phase 0 — Architecture & Setup 🟡 partial

**Done**
- `.github/workflows/mobile-ci.yml` — format gate, `analyze --fatal-infos`,
  tests, Android + iOS builds, integration tests on a booted simulator.
  Runs `build_runner` first: generated sources are gitignored, so without it the
  tree does not compile.
- `.github/workflows/backend-ci.yml` — three jobs:
  - `unit-tests` (`backend/tests`) — **blocking**
  - `legacy-tests` (root `tests/`) — **non-blocking** on purpose: 153 pass, 23
    fail, 1 collection error, all pre-existing. Flip `continue-on-error` off once
    green; do not delete the job to silence it.
  - `secret-scan` — gitleaks + a hard fail if any `.env` is ever tracked again.
- `backend/requirements-dev.txt` — minimal test deps (the full requirements pull
  paddlepaddle ~500MB that no test touches). Verified in a clean venv.
- **Repo-wide `dart format`** applied (42 of 117 files were non-compliant).

**Not done:** TLS, OpenAPI spec refresh (`routes.json` is stale — 43 of ~350
paths), signing config, store accounts, Figma.

### Phase 1 — Foundation & Rebrand ✅ ~90%

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

**Not done:** Crashlytics, biometric unlock, an offline-state component.

### Phase 2 — OCR Document Extraction 🟡 capture, queue and review done; export not started

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
- [ ] **Run the exit criterion end to end.** Every piece is built and covered,
      but the HO server is unreachable from a dev machine, so the full round
      trip — photograph offline, reconnect, review, export, open in Excel —
      has not been done against a live server.
- [ ] **Calibrate the quality thresholds against real store captures.** They
      are currently tuned on synthetic pages and printed-invoice assumptions
      (`_sharpnessReject` and friends in `capture_processor.dart`). Leaning
      lenient is deliberate: a false "retake" on a good page teaches users to
      ignore the gate.

### Phase 3 — Core Operations 🟡 3 of 5 pieces done

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

**Not done**
- [ ] **Settings** — the plan's server/theme/biometrics/cache/WhatsApp/
      diagnostics screen. `More` currently has Device Status, Configuration
      Status and Agent Settings; the rest is unbuilt.
- [ ] **Offline outbox + background sync** — no `outbox` table, no
      `workmanager` tick. This is the largest remaining piece of Phase 3 and
      the one Purchase Workspace (Phase 5) depends on.
- [x] ~~Supplier BFF endpoint~~ — **done.** `GET /api/mobile/v1/suppliers`
      serves the same query and the same `{suppliers: [...]}` payload with
      scope resolved from the JWT instead of a role gate, so purchase-manager
      and salesman logins finally get a supplier list. Deliberately narrow:
      supplier products, stock, matching, reports and the cross-store
      dashboards stay behind `require_admin_role`. The mobile sync now points
      at it and no longer sends `tenant_id` at all.
- [ ] Report results are not cached to Drift yet, so they are not readable
      offline. The `fetchedAt` stamp the plan requires is already plumbed
      through `ReportResult`; only the `report_cache` table is missing.

### Phase 4 — Procurement & Admin 🟡 2 of 4 modules done

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

**Not done**
- [ ] **Cycle & Refresh Console** (L) — the largest Phase 4 module, and the one
      with push-notification-on-completion, which needs Firebase (still
      unprovisioned, see §1.3).
- [ ] **Legacy Order Console** (L) — ~20 endpoints under `/api/legacy-order/*`
      covering store health, job trigger/monitor and qty check.
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

**Lesson worth keeping:** static analysis and widget tests passed the
`StatusCard` crash straight through. Run the app on a simulator as part of
verification — and make sure the widget tests actually *render* the widget,
which is what caught the infinite-width bug above. Both review bugs above
followed the same pattern: green tests, wrong on a phone. A screenshot is part
of verification, not a nicety.

---

## 5. Current state

- **Branch:** `bharath-develop`
- **Last commit:** `b192104` (the security fix — still the only committed work)
- **Uncommitted: 93 modified files + 34 untracked paths.** Everything in
  Phases 0–4 above lives in the working tree and nowhere else.

⚠️ **This is the single biggest continuity risk.** Several sessions of work sit
in one uncommitted tree with no branch protecting it. Commit before doing
anything else — the split below is a suggestion, `git add -A && git commit` is
better than losing it.

New mobile feature code lives in:
`features/document_extraction/` · `features/reports/` · `features/time_report/`
· `features/pass_gen/` · `features/master_data/presentation/` ·
`features/sync/` (live ops) · `core/di/capture_providers.dart`

### Verification commands (all currently green)

```bash
cd mobile
dart run build_runner build --delete-conflicting-outputs
dart format --output=none --set-exit-if-changed lib test integration_test  # exit 0
flutter analyze --fatal-infos                                              # No issues found
flutter test                                                               # 335 passed
flutter test integration_test -d <simulator-udid>                          # 5 passed
flutter build apk --release                                                # 67.2MB
flutter build ios --debug --no-codesign                                    # ok

cd ../backend
.venv/bin/python -m pytest tests/ -q                                       # 61 passed
```

Run the app: `flutter run --dart-define=NEXORA_API_BASE_URL=http://122.252.246.181:8443`

### Suggested commit split

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

---

## 6. Next steps, in order

The short list is in **▶ RESUME HERE** at the top. Everything still open,
grouped by phase:

**Phase 2 — one thing left, and it needs a server**
1. **Run the exit criterion against a live HO server.** Photograph offline,
   reconnect, review, export, open the workbook in Excel. Every piece is built
   and covered by tests, including a contract test over the workbook itself
   (`backend/tests/test_document_export.py`), but the round trip has never run
   against a real server — 122.252.246.181:8443 is unreachable from a dev
   machine.

**Phase 3 — reach the MVP milestone**
2. **Offline outbox + background sync** — largest remaining MVP piece;
   Phase 5's Purchase Workspace depends on it. Note that review edits go
   straight to the server today and simply report the failure when offline;
   the outbox is where they would become queueable.
3. **Settings** — server, theme, biometrics, cache, WhatsApp, diagnostics.
4. Cache report results to Drift so they read offline (`fetchedAt` is already
   plumbed through `ReportResult`; only the `report_cache` table is missing).

**Phase 4 — the two large consoles**
5. **Cycle & Refresh Console** — also needs Firebase for its
   push-on-completion, still unprovisioned (§1.3).
6. **Legacy Order Console** — ~20 endpoints under `/api/legacy-order/*`.

**Cross-cutting, do whenever the relevant code is next touched**

- The **More tab is now long enough that Sign out is below the fold.** Another
  entry wants grouping (or a submenu), not appending.
- Two things when the camera is next on real hardware: calibrate the quality
  thresholds (§2), and fix `CapturePages.filePath` holding an **absolute**
  path — the iOS app container UUID changes across reinstalls, so a queue that
  survives an app update finds its images missing. The uploader already fails
  such a batch cleanly rather than sending a truncated invoice; the fix is to
  store a path relative to the documents directory and resolve it at read time.

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

- Verify by **running**, not just analysing — the `StatusCard` crash proves why.
- Never invent an endpoint; read the router. `routes.json` is stale.
- Report status honestly, including percentages and what is *not* done.
- Comments explain **why**, not what.
- Do not commit without being asked.
