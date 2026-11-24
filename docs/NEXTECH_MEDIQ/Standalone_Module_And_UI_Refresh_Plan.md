# Standalone New-Module Build + Login/Sidebar Refresh — Plan (draft, not yet built)

Status: **planning only**. Nothing below is implemented yet.

Build location confirmed with owner: inside `desktop/nextech-mediq`, as a
new self-contained module folder. **Standalone by design** — code is
copied into the new module, not imported from `supplier-stock-client` or
any other MediQ module. No cross-module wiring. Queries/business logic
that already exist elsewhere are copied in and adapted, never referenced
live from their original module.

`OPENAI_API_KEY` is set in `backend/.env` (expires 2026-11-30) — used only
during this development window for generating design assets (icons,
illustration images) for the new module, the login page, and sidebar.
Usage will be tracked and reported at the end (§5).

---

## 1. Token-save working rule for this build (standing, not optional)

Per owner instruction: **do not read the whole app or whole modules.**
For every piece of "we already have this query/design, just copy it":
1. Grep the specific function/query name only (e.g. `qty_check_order_history`,
   not the whole `repository.py`).
2. Read only the matched line range (`offset`/`limit`), never the full
   file, unless that file *is* the thing being copied wholesale.
3. Copy the matched code into the new module's own file. Do not leave an
   import pointing back at the source module.
4. Never open `supplier-stock-client` to "check how it's done" — if a
   pattern is needed from there, ask which specific file/function first,
   then read only that.

This rule applies to every phase below, including the AI-asset generation
phase (ask for one icon/image at a time, don't batch-generate speculative
assets).

---

## 2. Phases

### Phase 0 — Confirm scope of "the new module"
Before building anything: which existing screen/workflow is this new
standalone module actually replacing or adding? (Not yet named by the
owner in this conversation — needs confirming before Phase 1 starts,
otherwise "copy the query/design we already have" has no target.)

### Phase 1 — Login page redesign
- Keep `LoginPage.jsx`'s existing structure (brand pane + form pane,
  `useAuth().login`) — only visual/asset layer changes, not the auth flow.
- Generate 1-2 new background/hero illustration assets via OpenAI image
  API, styled to match `BrandLockup` (pharma/clinical, modern, dark-pane
  friendly) — stored under the new module's own `assets/` folder, not
  shared globally.
- Refresh `login.css`: modern glass/gradient card treatment, animated
  focus states, consistent with existing dark-pane brand colors (read
  `BrandLockup.jsx`'s variant tokens only, not the whole component tree).
- Feature-highlight icons (`inventory`, `procurement`, `reports`, `spark`)
  can be regenerated as a consistent icon set via OpenAI image API if the
  current `Icon` set looks dated — owner to confirm after first draft.

### Phase 2 — Sidebar fix
- Current `Sidebar.jsx` issue to diagnose precisely (read only this file,
  already done — 60 lines read, accordion-group logic looks fine
  structurally): "still not looking good" is a *visual* complaint, so
  this is a CSS/spacing/icon-alignment pass, not a logic rewrite.
- Needs the matching stylesheet identified and read (not yet located in
  this pass — next step is `find` for the sidebar's CSS file, read only
  that file).
- Likely fixes: consistent icon sizing/alignment, active-state contrast,
  group-header spacing, collapsed-state icon-only layout polish.
- New icons (if needed) generated via OpenAI image API, same asset
  folder as Phase 1.

### Phase 3 — Standalone module build
- Once Phase 0 names the target workflow: copy its existing query/repo
  logic and any existing frontend design patterns into the new module's
  own files (per §1 rule — targeted reads only, no whole-file/whole-module
  scans unless copying a whole file verbatim).
- New module gets its own `assets/` subfolder for any OpenAI-generated
  icons/images it needs, kept local to the module.
- No imports from other MediQ modules or from `supplier-stock-client`.

### Phase 4 — Copy to supplier-stock-client and web
- Once the new module is finalized and working standalone in
  nextech-mediq, copy the finished module (components, queries, assets)
  into `supplier-stock-client` and the web frontend as their own standalone
  copies — same "no cross-module wiring" rule applies in each destination.
- This is a copy, not a shared package — each app keeps its own copy per
  owner's existing standing instruction that these apps don't share code
  at runtime.

### Phase 5 — OpenAI usage report
At the end of this build, report:
- Number of image-generation calls made and their resolutions/model.
- Number of any text/completion calls (if used for design copy/content).
- Estimated cost based on OpenAI's published per-image/per-token pricing
  at call time.
- Reminder that the key expires 2026-11-30 — flag if any phase will run
  past that date.

---

## 3. Open items before Phase 0 can close
- What workflow/screen is "the new module" actually for? Not yet stated.
- Confirm sidebar's CSS file path before Phase 2 edits (next session
  step: locate it with a targeted search, read only that file).
- Confirm whether "modern login page" means a full visual overhaul or a
  lighter refresh — Phase 1 draft will clarify by showing a first pass.

## 4. What stays untouched
- `AuthContext.jsx` login flow, token handling, `remember` logic.
- Sidebar's accordion/group-toggle logic (`Sidebar.jsx` lines 38-48) —
  this is a visual fix only, confirmed working logic is not touched.
- Any other MediQ module's existing code — new module stays standalone,
  nothing else is refactored to accommodate it.
