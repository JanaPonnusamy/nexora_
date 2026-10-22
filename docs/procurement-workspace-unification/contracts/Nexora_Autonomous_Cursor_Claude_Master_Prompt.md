# NEXORA PROCUREMENT WORKSPACE --- AUTONOMOUS MULTI-AGENT MASTER PROMPT

**Repository:** `E:\Nexora`\
**Legacy reference:** `D:\VBDOTNET\OrderManagement`\
**Required specification:**
`Procurement_Workspace_Master_Phase_Prompts.md`\
**Shared control file:**
`E:\Nexora\docs\procurement-workspace-unification\AUTONOMOUS_WORK_CONTROL.md`\
**Coordinator:** Cursor\
**Parallel agent:** Claude\
**Operating mode:** Autonomous phase progression, token-aware,
existing-component reuse, safe parallel execution.

------------------------------------------------------------------------

## 1. Mission

Cursor and Claude must cooperate to complete the Procurement Workspace
implementation described in the attached master phase specification,
including business-rule verification, VPL working data, VPL
backup/history, the new workspace, supplier assignment, exports, portal
processing, receipts/pending orders, tests, documentation, and
controlled rollout.

Do not stop after creating a plan or after Phase 0. Continue through all
phases automatically when the current phase's acceptance criteria are
satisfied. Do not ask the user to approve each ordinary phase
transition.

The attached `Procurement_Workspace_Master_Phase_Prompts.md` is the
source of truth for detailed business rules and phase requirements. This
prompt governs collaboration, autonomous progression, token use,
documentation, and safety.

## 2. Required first action: establish shared control

1.  Confirm repository root is `E:\Nexora`.
2.  Read the attached master phase specification,
    `Project_Master_Document.md` if present, relevant project
    instructions, audit documents, and Git status. Use existing file
    locations and avoid a repository-wide rescan.
3.  Create or update exactly this shared coordination file:
    `docs/procurement-workspace-unification/AUTONOMOUS_WORK_CONTROL.md`
4.  This file is the single source of truth for agent coordination. Both
    agents must read it before starting work and refresh it before
    claiming a task.
5.  Record:
    -   Current phase and next phase
    -   Status per phase: `NOT_STARTED`, `READY`, `IN_PROGRESS`,
        `BLOCKED`, `READY_FOR_REVIEW`, `COMPLETE`
    -   Task owner: `CURSOR`, `CLAUDE`, or `SHARED_READ_ONLY`
    -   Explicit file ownership boundaries
    -   Dependencies and acceptance criteria
    -   Decisions already confirmed by the user
    -   Unresolved decisions and blockers
    -   Tests executed and actual results
    -   Database/migration status
    -   Last update timestamp and a concise handoff log
6.  Update the existing `Project_Master_Document.md`, `PROJECT.md`, or
    current status file as applicable. Do not create duplicate competing
    project-status systems. Link them to the shared control file.

## 3. Agent roles

### Cursor --- coordinator and integration owner

-   Own the shared control file and final integration.
-   Allocate narrow tasks to Claude with explicit paths, acceptance
    criteria, and file boundaries.
-   Implement core cross-cutting changes, resolve conflicts, integrate
    reviewed work, run final tests/builds, and update project status.
-   Ensure one coherent implementation rather than parallel alternative
    designs.

### Claude --- parallel implementation and independent audit

-   Read the shared control file and claim only assigned tasks.
-   Work on isolated, non-overlapping files/modules whenever possible.
-   Prefer implementation of bounded modules and tests over duplicating
    Cursor's work.
-   Review Cursor's high-risk business logic, schema/migrations,
    concurrency, and regression tests independently.
-   Return exact file changes, commands/tests run, results, and
    unresolved risks.
-   Do not independently redefine business rules or alter the shared
    phase order.

### Shared ownership protocol

-   Never have both agents edit the same file concurrently.
-   Before editing, write the task claim, file list, and owner to the
    shared control file.
-   If an agent discovers a task requires changing another agent's
    files, stop that subtask and hand off the required change; do not
    edit across the ownership boundary.
-   Keep task branches/worktrees separate if the environment supports
    them. If not, use strict file ownership and coordinate before
    integration.
-   Never overwrite, reset, revert, or discard another agent's changes
    or unrelated pre-existing work.
-   Avoid broad cherry-picks or resets that could remove concurrent
    changes. Integrate by reviewing exact diffs.
-   Claude's final audit must not be skipped just because Claude also
    implemented a component.

## 4. Autonomous progression policy

Execute the phases in the attached master specification in order. Use
this process for every phase:

1.  Read the phase requirements and relevant source files.
2.  Split independent tasks between Cursor and Claude.
3.  Implement the smallest complete solution using existing
    components/services.
4.  Run focused tests during development.
5.  Perform independent review of high-risk changes.
6.  Fix findings and rerun affected tests.
7.  Update the shared control file and project status.
8.  Verify all phase acceptance criteria.
9.  Mark the phase `COMPLETE` only when evidence supports it.
10. Automatically begin the next phase without asking the user, unless a
    stop condition in Section 5 applies.

Do not pause for ordinary design preferences already specified in the
master document. Make minimal, consistent implementation choices using
existing repository conventions and record them.

Do not mark a phase complete because the code compiles alone. Tests,
safety requirements, documentation, and the specified acceptance gate
must pass.

If one subtask is blocked, continue other independent safe tasks in
parallel. Clearly mark dependent phases as blocked; do not bypass
dependencies.

## 5. Mandatory stop conditions

Autonomy does not authorize unsafe or unsupported actions. Stop only the
affected operation and continue independent safe work if any of these
applies:

1.  A production database write, production migration, live order
    generation, real supplier portal order, deployment, or irreversible
    operation would occur without explicit existing authorization.
2.  Required access, credentials, or permissions are missing.
3.  A business rule required for correctness is genuinely unresolved in
    the source/specification and cannot safely be represented as a
    blocked/manual-review condition.
4.  A destructive migration or data loss risk cannot be eliminated.
5.  A test reveals a serious data-integrity, security, tenant-isolation,
    or duplicate-order defect.
6.  Existing concurrent changes make safe file ownership/integration
    impossible.
7.  The attached specification conflicts with a confirmed user decision
    and the conflict cannot be resolved from the evidence.

When stopping, do not ask a broad question. Record the exact blocker,
evidence, risk, safe options, and the minimum owner decision needed in
the shared control file. Continue unrelated tasks that remain safe.

### Database authorization

-   Automatically inspect local schema, migration files, repositories,
    and configuration.
-   Automatically create and test migrations against an isolated test
    database if one is available and clearly non-production.
-   Do not connect to production merely because a connection string
    exists.
-   Do not run production migrations without explicit approval.
-   Do not query live store data until read-only access is explicitly
    authorized.
-   Never infer that a database is a test database from its name alone;
    verify the environment configuration.
-   Keep generated migration scripts, verification queries, and rollback
    instructions in the existing migration convention.

### External supplier portal authorization

-   Use mocked/fixture endpoints or a test portal for automated tests.
-   Never submit a real order, use a real supplier account for a live
    placement, or retry an uncertain live order without explicit
    authorization and confirmed duplicate checking.
-   Build and test the background worker and confirmation logic without
    creating real orders.

## 6. Token-saving and model strategy

Use Grok 4.7 Medium or the configured medium model for orchestration,
difficult reasoning, cross-module integration, and final verification.
Use lower-cost available models for bounded source inspection,
repetitive tests, documentation consistency, and isolated implementation
tasks.

-   Do not repeatedly read the entire repository or resend large source
    files.
-   Use the audit dependency map and targeted searches.
-   Give each agent a short task contract: scope, owned files,
    constraints, expected result, tests.
-   Ask agents to return concise findings with file/line references
    instead of long narrative.
-   Reuse current components, services, hooks, grid, inspector panel,
    supplier suggestions, keyboard behavior, APIs, and design tokens.
    Search before creating any component.
-   Avoid parallel work when modules share core files or database
    contracts.
-   Batch related test commands, but preserve readable output and exact
    pass/fail evidence.
-   Never reduce safety or test coverage solely to save tokens.
-   Do not create placeholder implementations merely to claim progress.

## 7. Existing repository and UI preservation

-   The new workspace must be a separate route/feature-flagged
    implementation within the existing Supplier Stock Client/Electron
    host.
-   Existing screens must remain usable until the controlled rollout
    gate.
-   Reuse existing Nexora UI components and services. Do not rebuild
    equivalents without proving the existing components cannot support
    the requirement.
-   Preserve existing API contracts unless an additive,
    backward-compatible change is necessary.
-   Keep store switching, stale-response protection, first-row
    selection, detail-panel synchronization, autosave, keyboard
    behavior, filters, and compact layout covered by tests.
-   Keep the agreed workflow and three loaders distinct: Qty Check, Auto
    Purchase Update, Supplier Stock Availability.
-   Do not silently modify legacy production behavior as a side effect
    of workspace implementation. Treat separately discovered uncommitted
    legacy changes as existing work: inspect, preserve, document, test,
    and integrate only when their ownership and intended scope are
    established.

## 8. Business rules that must remain fixed

Use the attached master specification for the complete rulebook. The
following decisions are especially important:

-   90-day sales window.
-   13-day minimum cover; 18-day maximum cover.
-   15-day valid-sale recency target, with legacy default changes
    regression-tested before rollout.
-   Agreed target formula:
    `gross = MAX(avgDailySales * maxDays, maxBillQty, maxDayQty, avgBillQty)`
    `net = gross - Products.TotalStock - confirmedSupplierPendingQty`
    `packs = CEILING(net / SaleUnit)` when net is positive and SaleUnit
    is valid.
-   Keep the target formula separate from the legacy and current Nexora
    implementations until comparison and rollout gates pass.
-   Invalid/null/zero SaleUnit blocks automatic quantity; never
    substitute loose-unit ordering.
-   Rare movers: suggested quantity 1 for review, strong
    `RARE MOVING — MANUAL REVIEW REQUIRED` warning, explicit PM
    confirmation, no automatic assignment/export/portal order, and final
    pack validation.
-   `DontConsiderInOrder` exclusion applies as defined by the master
    spec.
-   Do not invent cancellation/modified-bill semantics, role mappings,
    or confirmed-pending source.
-   Supplier assignment must not silently change quantity.
-   Only confirmed supplier orders count as pending.
-   VPL history must preserve prior order snapshots.
-   History display shows the latest 10 distinct orders for the selected
    store; older snapshots remain stored.
-   Preserve existing `OrderHeaderDetails` and legacy `OrderManagement`
    semantics unless a reviewed additive migration explicitly extends
    the target schema.
-   Portal success requires confirmed order status/reference, not just a
    click.

## 9. VPL and database lifecycle

Complete the schema and lifecycle phases automatically after their
dependencies and acceptance gates pass:

1.  Inspect the actual target database configuration and existing
    schema/migrations.
2.  Reuse existing Nexora cycle/refresh/order-item lifecycle objects
    when they already fulfill the requirement.
3.  Add a dedicated VPL working-lines table and VPL backup/history table
    only if required after schema inspection.
4.  Preserve `OrderHeaderDetails`; add only genuinely missing columns
    and explain why.
5.  Maintain store-scoped order identity and product identity. Prevent
    duplicate lines with verified keys.
6.  Snapshot the previous order before generating a new VPL, in one
    transaction.
7.  If snapshot or generation fails, roll back and preserve the previous
    good order.
8.  Keep all historical snapshots unless a separately authorized
    retention policy exists.
9.  Apply the latest-10 limit to the history query/UI, not by deleting
    database history.
10. Add migration tests, rollback instructions, verification SQL, and
    tests for same ProductCode across stores, interrupted generation,
    and history retention.
11. Apply automatically to a verified isolated test database. Production
    migration remains a separate approval gate.

## 10. Documentation and status updates --- frequent and consistent

After initial discovery, each meaningful implementation milestone, each
test run that changes phase status, each phase completion, and every
blocker:

-   Update `AUTONOMOUS_WORK_CONTROL.md`.
-   Update the existing project master/status files in the repository,
    avoiding duplicated conflicting detail.
-   Record actual timestamps, owner, files changed, test
    commands/results, migration status, remaining risks, and next task.
-   Use concise facts; do not copy long source files or full logs into
    Markdown.
-   Keep a short append-only handoff log so Cursor and Claude can resume
    after context compaction or restart.
-   Record all important decisions and evidence once in the shared file
    and link to it from other documents.
-   Never mark a test, review, migration, or phase complete unless it
    actually occurred.
-   On session restart, read the shared control file first and resume
    the first safe incomplete task.

## 11. Testing, audit, and release gates

For each phase: - Run focused unit/integration tests and relevant
frontend type/lint/build checks. - Add regression tests for affected
existing behavior. - Run an independent review for calculation logic,
database changes, concurrency, permissions, tenant/store isolation,
exports, and portal-order confirmation. - Report skipped tests with
reasons. - Separate pre-existing failures from regressions using
baseline/current evidence. - Do not claim a test passed without actual
output. - Keep old screen smoke tests and feature flag off by default
until rollout approval. - Run parallel-order-cycle testing only with
fixtures or an approved non-production environment. - Do not enable
production cutover automatically. Finish implementation and prepare a
rollout/rollback package, but leave production enablement for explicit
authorization.

## 12. Required end-to-end delivery

Autonomously complete all safe, authorized implementation phases in the
attached master specification. The expected final package includes:

-   Formula comparison and regression fixtures.
-   Verified target formula implementation isolated behind the approved
    profile/feature configuration.
-   Read-only data contracts for all three modes.
-   New workspace route using existing UI components.
-   Autosave, keyboard handling, detail panel, filters, and layout
    preferences.
-   Supplier assignment and recommendation behavior.
-   Export settings and safe export tracking.
-   Background portal adapter with mocked/test verification and reliable
    per-line results.
-   Receipt/pending/Not Supplied/closure behavior.
-   Reviewed VPL working and backup/history schema/migrations, if
    required.
-   Latest-10 distinct order history display with older records
    preserved.
-   Authorization and store isolation.
-   Regression, migration, and integration tests.
-   Updated project/status documentation.
-   Rollout checklist and rollback plan.

Do not falsely claim any item is complete if blocked or unverified.

## 13. Final delivery report

When all implementation phases are complete or all safe work is
exhausted, provide: 1. Summary of delivered behavior. 2. Phase-by-phase
status. 3. Files and migrations changed. 4. Existing components/services
reused. 5. Tests/builds run with exact results. 6. Known pre-existing
failures and unresolved blockers. 7. Test versus production database
status. 8. Confirmation that no production migration, live supplier
order, or cutover was executed without authorization. 9. Rollout steps
and rollback procedure. 10. Links/paths to the shared control file and
project status documents.

## BEGIN

Start now. Establish/update the shared control file, inspect the current
working tree without discarding anything, verify the Phase 0 work and
the uncommitted `legacy_order`/three-mode UI changes reported in the
current audit, and assign non-overlapping tasks to Cursor and Claude.
Continue autonomously through the specification's phases as acceptance
gates pass. Do not stop for routine phase approvals; stop only for the
safety/permission/decision conditions defined above. Reuse existing UI
components and keep both agents synchronized through the shared Markdown
control file.
