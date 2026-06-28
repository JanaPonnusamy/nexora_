# NEXORA Development Framework (NDF)

## Technical Architecture Document

> **Module:** NEXORA Development Framework (NDF)
> **Type:** Platform Module — peer of Authentication, Sync, Procurement
> **Status:** Architecture for sign-off + reference for the bundled implementation
> **Repository:** https://github.com/JanaPonnusamy/nexora_
> **Runtime:** Python 3.12, standard library only (no third-party dependencies)
> **Independence:** Self-contained under `automation/`. Does **not** modify Procurement, Sync, backend, or frontend.

---

## 1. Purpose and Scope

### 1.1 Purpose

The NEXORA Development Framework (NDF) is an **enterprise development automation framework** that governs
the engineering lifecycle of the NEXORA platform. Before Procurement V1 is implemented, NDF establishes the
machinery that automates:

- **GitHub synchronization** — change detection, intelligent commit grouping, standardized messages, push, tags.
- **Version management** — a single, machine-readable `VERSION.md`.
- **Changelog & release notes** — structured, generated from versioned history.
- **Documentation governance** — an auto-built documentation index, ADRs, and a business-rule registry.
- **Project governance** — a project dashboard, AI-documentation archive, and repository health reporting.

### 1.2 Treated as a Platform Module

NDF is a first-class platform module. Like Authentication or Sync it has a defined boundary, a layered
internal architecture, a configuration contract, and a command surface. It is **not** a bag of helper
scripts. All behaviour is driven by configuration and exposed through a stable CLI.

### 1.3 Scope

| In scope | Out of scope |
|----------|--------------|
| Versioning, changelog, release notes | CI/CD pipeline definitions (NDF can be *invoked* by CI) |
| GitHub sync via local `git` CLI | Hosting, deployment, infrastructure |
| Docs index, ADRs, business-rule registry | Authoring document *content* (NDF indexes/structures it) |
| Project dashboard, AI archive, repo health | Modifying Procurement / Sync / backend / frontend logic |

### 1.4 Independence guarantee

NDF lives entirely under `automation/` plus a small set of **generated artifacts** at the repo root and under
`docs/`. It reads the repository; it never imports from or edits `backend/`, `frontend/`, `store_agent/`,
Procurement, or Sync. Removing the `automation/` package and the generated artifacts fully removes NDF.

---

## 2. Architectural Principles

1. **Configuration-driven.** No hardcoded paths, module names, or thresholds. Everything resolves from
   `ndf.config.toml` (or bundled defaults). Adding a new vertical (Inventory, Sales, Hospital, Garments,
   Manufacturing) is a configuration change, **not** a code change.
2. **Layered + SOLID.** Strict separation: Commands → Services → Builders/Providers → Core. Dependencies point
   inward. Each class has a single responsibility.
3. **Dependency Injection.** Services receive their collaborators (providers, builders, config, logger) through
   a lightweight container. No service constructs its own infrastructure or reaches for globals.
4. **Repository/Provider pattern for I/O.** All side effects — filesystem, git, clock, environment — are behind
   provider interfaces, making services deterministic and testable.
5. **Typed models.** All data crossing layer boundaries is a typed dataclass, not a loose dict.
6. **Stdlib-only.** Python 3.12 standard library exclusively (`tomllib`, `pathlib`, `subprocess`, `dataclasses`,
   `logging`, `datetime`, `json`, `re`). Zero supply-chain footprint; nothing to install.
7. **Idempotent & safe.** Generators are idempotent — re-running produces the same artifact for the same input.
   Mutating git operations are explicit, logged, and never force-push or skip hooks.
8. **Future-ready by data, not by code.** New modules, sections, commit-type mappings, and rule prefixes are all
   declared in configuration.

---

## 3. Layered Architecture

```
                    ┌─────────────────────────────────────────────────────────┐
   CLI entrypoints  │  python -m automation.<group> <action>                   │
   (runnable)       │  python -m automation <group> <action>   (unified)       │
                    └───────────────────────────┬─────────────────────────────┘
                                                 ▼
   COMMANDS         Parse argv → build context → invoke a service → render result
   (automation/commands)        version · docs · release · github · dashboard · rules · adr · ai · health
                                                 ▼
   SERVICES         Business logic / orchestration (one service per capability)
   (automation/services)        VersionService · ChangelogService · ReleaseService · GitHubSyncService
                                DocsRegistryService · AdrService · BusinessRuleService · DashboardService
                                AiArchiveService · RepoHealthService
                          │                                   │
                          ▼                                   ▼
   BUILDERS                                    PROVIDERS
   (automation/builders)  pure render: model→text            (automation/providers)  side effects behind interfaces
     MarkdownBuilder, VersionBuilder,                          FileSystemProvider, GitProvider,
     ChangelogBuilder, ReleaseNotesBuilder,                    ClockProvider, EnvironmentProvider
     IndexBuilder, DashboardBuilder,
     AdrBuilder, RuleBuilder
                          │                                   │
                          └───────────────┬───────────────────┘
                                          ▼
   CORE             Config · PathResolver · Logging · Models · Result · Exceptions · Container (DI)
   (automation/core)
                                          ▼
   TEMPLATES        Text templates for generated documents (automation/templates)
```

**Dependency rule:** Commands depend on Services; Services depend on Builders, Providers, and Core; Builders and
Providers depend only on Core. Core depends on nothing inside NDF. Templates are data consumed by Builders.

---

## 4. Folder Structure

```
automation/
├── __init__.py                 # NDF package metadata (NDF's own version)
├── __main__.py                 # unified dispatcher: python -m automation <group> <action>
├── README.md
│
├── core/                       # framework foundation (no side effects)
│   ├── config.py               # NDFConfig + loader (tomllib, defaults, env override)
│   ├── paths.py                # PathResolver — repo-root + configured relative paths
│   ├── logging.py              # logger factory, configuration-driven
│   ├── models.py               # typed dataclasses (VersionInfo, DocRecord, AdrRecord, BusinessRule, …)
│   ├── result.py               # CommandResult value object
│   ├── exceptions.py           # NDFError hierarchy
│   └── container.py            # lightweight DI container / composition root
│
├── providers/                  # side effects behind interfaces (Repository/Provider pattern)
│   ├── filesystem.py           # FileSystemProvider — read/write/glob/exists
│   ├── git_provider.py         # GitProvider — status/add/commit/push/pull/tag/branch (git CLI)
│   ├── clock.py                # ClockProvider — now()/today()
│   └── environment.py          # EnvironmentProvider — developer identity, env vars
│
├── services/                   # capability logic
│   ├── version_service.py
│   ├── changelog_service.py
│   ├── release_service.py
│   ├── github_sync_service.py
│   ├── docs_registry_service.py
│   ├── adr_service.py
│   ├── business_rule_service.py
│   ├── dashboard_service.py
│   ├── ai_archive_service.py
│   └── repo_health_service.py
│
├── builders/                   # pure model→text rendering
│   ├── markdown.py             # MarkdownBuilder (tables, sections, frontmatter)
│   ├── version_builder.py
│   ├── changelog_builder.py
│   ├── release_notes_builder.py
│   ├── index_builder.py
│   ├── dashboard_builder.py
│   ├── adr_builder.py
│   └── rule_builder.py
│
├── templates/                  # document templates (text)
│   ├── loader.py
│   ├── version.md.tmpl
│   ├── adr.md.tmpl
│   ├── business_rule.md.tmpl
│   └── release_notes.md.tmpl
│
├── commands/                   # CLI command handlers
│   ├── base.py                 # BaseCommand (arg parsing helpers, container access)
│   ├── version_cmd.py
│   ├── docs_cmd.py
│   ├── release_cmd.py
│   ├── github_cmd.py
│   ├── dashboard_cmd.py
│   ├── rules_cmd.py
│   ├── adr_cmd.py
│   ├── ai_cmd.py
│   └── health_cmd.py
│
├── config/
│   └── ndf.config.toml         # bundled default configuration
│
├── version.py                  # runnable shim → commands.version_cmd
├── docs.py                     # runnable shim → commands.docs_cmd
├── release.py                  # runnable shim → commands.release_cmd
├── github.py                   # runnable shim → commands.github_cmd
├── dashboard.py                # runnable shim → commands.dashboard_cmd
└── rules.py                    # runnable shim → commands.rules_cmd

# Generated artifacts (owned by NDF, live at conventional locations)
VERSION.md
CHANGELOG.md
RELEASE_NOTES.md
PROJECT_STATUS.md
ndf.config.toml                 # optional project-level override (repo root)
docs/INDEX.md
docs/ADR/ADR-XXX-*.md
docs/BUSINESS_RULES/<PREFIX>-BR-XXX-*.md  + registry.json
docs/AI_ARCHIVE/ ...
docs/REPORTS/repo_health.md
```

> The top-level shims (`automation/version.py`, …) exist solely so the exact published command
> `python -m automation.version bump minor` works. They contain one line each and delegate to the Commands layer.

---

## 5. Configuration Contract

Configuration precedence (highest wins):

1. Path in environment variable `NDF_CONFIG`.
2. `ndf.config.toml` at the repository root (project override).
3. Bundled defaults in `automation/config/ndf.config.toml`.

All filesystem locations are **relative to the auto-detected repository root** (via `git rev-parse`, falling
back to walking up for a `.git` directory). There are **no absolute paths** anywhere in the framework.

Key configuration groups:

| Group | Drives |
|-------|--------|
| `[project]` | name, repository URL, default branch. |
| `[paths]` | every generated-artifact location (relative). |
| `[version]` | release name, build-number policy. |
| `[changelog]` | the ordered changelog sections (Added, Changed, Fixed, Removed, Deprecated, Security, Performance). |
| `[commit]` | mapping of conventional-commit types → changelog sections, and commit-message format. |
| `[github]` | remote name, auto-tag policy, push policy. |
| `[health]` | large-file threshold, document extensions, orphan rules. |
| `[modules]` | the platform module registry (name, status, completion, owner) for the dashboard & governance. |
| `[rules]` | business-rule prefixes per module (e.g. Procurement → `PR-BR`). |
| `[ai]` | AI archive sources (ChatGPT, Claude) and approval states. |

Because modules, rule prefixes, commit mappings, and changelog sections are **all configuration**, supporting a
new vertical (Inventory, Sales, Hospital, Garments, Manufacturing) requires **no code change** — satisfying the
Future-Ready requirement.

---

## 6. Domain Models (Typed)

All inter-layer data is a dataclass. Principal models:

| Model | Fields (summary) |
|-------|------------------|
| `VersionInfo` | major, minor, patch, build_number, build_date, release_name, developer, git_commit, branch. |
| `ChangelogEntry` | section, summary, commit_hash, scope, date. |
| `ReleaseNotes` | version, date, highlights, grouped entries. |
| `DocRecord` | module, document, path, version, status, owner, updated_date. |
| `AdrRecord` | number, title, status, date, context-link, path. |
| `BusinessRule` | id (`<PREFIX>-BR-NNN`), name, module, version, priority, status, dependencies, description. |
| `ModuleStatus` | name, status, completion_pct, owner, milestone. |
| `AiArtifact` | source (ChatGPT/Claude), kind (prompt/output), approval_status, revision, date. |
| `HealthFinding` | category (large/duplicate/broken-link/missing-doc/orphan), target, detail, severity. |
| `CommandResult` | ok, message, changed_paths, data. |

---

## 7. Providers (Side-Effect Boundary)

| Provider | Responsibility | Notes |
|----------|----------------|-------|
| `FileSystemProvider` | read/write text, glob, exists, ensure-dir | All writes route here; enables dry-run & testing. |
| `GitProvider` | branch, status (porcelain), add, commit, push, pull, tag, list-tags, rev-parse, log | Wraps the local `git` CLI via `subprocess`. **Never** `--force`, **never** `--no-verify`. |
| `ClockProvider` | `now()`, `today()` | Single source of time → deterministic build dates in tests. |
| `EnvironmentProvider` | developer identity (git `user.name`/env), env vars | Feeds the `Developer` field of `VERSION.md`. |

Services depend on provider **roles**, not concretions, so behaviour (e.g., dry-run filesystem) can be swapped via
the container.

---

## 8. Feature Designs

### 8.1 Automatic GitHub Sync (`github sync`)
1. **Detect** changed files via `git status --porcelain`.
2. **Group** changes intelligently by top-level area (backend, frontend, store_agent, docs, automation, tests, …)
   using configured grouping rules — each group becomes one logical commit.
3. **Standardize** messages: `<type>(<scope>): <summary>` derived from the group + a generated body listing files.
4. **Push** to the configured remote/branch (current branch auto-detected; never the wrong branch).
5. **Tag** optionally (when `--tag` or `[github].auto_tag`) with the current version.

Safety: refuses to operate on a detached HEAD silently; logs every git invocation; honours hooks.

### 8.2 Version Management (`version bump|show|set`)
`VERSION.md` carries a machine-readable fenced block (the single source of truth) plus rendered prose. A bump:
- increments Major / Minor / Patch / Build per the requested level (build auto-increments on every bump),
- refreshes Build Date (ClockProvider), Developer (EnvironmentProvider), Git Commit + Branch (GitProvider),
- preserves Release Name unless overridden,
- re-renders `VERSION.md` idempotently.

### 8.3 Changelog Generator (`docs changelog` / part of `release build`)
Collects entries since the last version tag from git history, maps conventional-commit types → the configured
sections (**Added, Changed, Fixed, Removed, Deprecated, Security, Performance**), merges any staged manual
entries, and writes/updates `CHANGELOG.md` under a "Keep a Changelog"-style layout.

### 8.4 Release Notes Generator (`release build`)
For a milestone/version, produces `RELEASE_NOTES.md` from the version + changelog sections, with highlights and a
full categorized list. Optionally creates the git tag and a changelog release header.

### 8.5 Documentation Registry (`docs build`)
Scans the docs tree, derives `DocRecord`s (module/document/version/status/owner/updated-date from file frontmatter
or conventions), and renders `docs/INDEX.md` (Module · Document · Version · Status · Owner · Updated Date). Also
refreshes the ADR index and business-rule index, and runs link checks feeding repo health.

### 8.6 Architecture Decision Records (`adr new|list`)
`docs/ADR/` with **automatic sequential numbering** (`ADR-001`, `ADR-002`, …). `adr new "<title>"` finds the next
number, instantiates the ADR template (Status: Proposed, dated), and links it into the ADR index. Examples seeded:
ADR-001 Shared Sync Tables, ADR-002 Business Cycle, ADR-003 Refresh Engine, ADR-004 Procurement Workspace,
ADR-005 Pending Architecture.

### 8.7 Business Rule Registry (`rules register|list`)
`docs/BUSINESS_RULES/` with a JSON registry as source of truth + generated index. Each rule gets a **permanent
identifier** `<PREFIX>-BR-NNN` (prefix per module from config, e.g. Procurement → `PR-BR`). Rules carry **Version,
Module, Priority, Status, Dependencies**. IDs are never reused. Example: `PR-BR-001` 90 Day Average,
`PR-BR-002` Min Day Rule.

### 8.8 Project Dashboard (`dashboard build`)
Generates `PROJECT_STATUS.md`: overall completion (rollup of module completion from `[modules]`), per-module
completion, milestones, recent work (from git log), current version (from `VERSION.md`), and pending work.

### 8.9 AI Documentation Archive (`ai add|approve|reject|list`)
`docs/AI_ARCHIVE/` retains Prompt History, Approved Outputs, Rejected Outputs, and Revision History, each tagged
with **AI Source** (ChatGPT / Claude) and **Approval Status**. Provides provenance for AI-generated documentation.

### 8.10 Repository Health (`health report`)
Generates `docs/REPORTS/repo_health.md` covering Large files, Duplicate documents (content hash), Broken links
(within Markdown), Missing documentation (modules lacking docs), and Orphan files (unreferenced docs).

### 8.11 Developer Commands
Published command surface (exact forms):
```
python -m automation.version bump minor
python -m automation.docs build
python -m automation.release build
python -m automation.github sync
python -m automation.dashboard build
python -m automation.rules register
```
Plus the unified dispatcher `python -m automation <group> <action>` and groups `adr`, `ai`, `health`.

---

## 9. Coding Standards

- **Python**, FastAPI-compatible (importable from the platform; shares no global state with it).
- **SOLID**, single-responsibility classes; small, composable units.
- **Dependency Injection** via the `core/container.py` composition root.
- **Repository/Provider pattern** for all I/O.
- **Logging** through the central logger factory (configuration-driven level/format); no `print` for logic.
- **Configuration-driven**; **no hardcoded paths**.
- **Typed models** (dataclasses) at every boundary; type hints throughout.
- Idempotent generators; explicit, audited git mutations.

---

## 10. Error Handling & Logging

- All framework errors derive from `NDFError` (`ConfigError`, `GitError`, `PathError`, `RegistryError`, …).
- Commands catch `NDFError`, log it, and return a non-zero exit with a `CommandResult` message — they never leak
  stack traces to normal users (full traceback only at debug log level).
- Every git mutation and every file write is logged at INFO; reads at DEBUG.

---

## 11. Extensibility / Future-Ready

Adding a vertical (e.g., **Inventory**) requires only configuration:

1. Add the module to `[modules]` (name, owner, status, completion) → appears in the dashboard and health checks.
2. Add its rule prefix to `[rules]` (e.g., `IN-BR`) → `rules register --module Inventory` issues `IN-BR-001…`.
3. Author its docs with standard frontmatter → indexed automatically by `docs build`.

No NDF source file changes. The same holds for Sales, Hospital, Garments, and Manufacturing.

---

## 12. Non-Goals / Boundaries

- NDF does not build, test, or deploy application code (it can be *called* from CI to do its own tasks).
- NDF does not author document content; it indexes, structures, and governs it.
- NDF never edits Procurement, Sync, backend, frontend, or Store Agent source.

---

## 13. Appendix — Command Reference

| Command | Action |
|---------|--------|
| `python -m automation.version bump {major\|minor\|patch\|build}` | Bump version, refresh `VERSION.md`. |
| `python -m automation.version show` | Print current version. |
| `python -m automation.docs build` | Build `docs/INDEX.md`, ADR & rule indexes, link checks. |
| `python -m automation.release build` | Generate `CHANGELOG.md` + `RELEASE_NOTES.md` (optional `--tag`). |
| `python -m automation.github sync` | Detect, group, commit, push (optional `--tag`). |
| `python -m automation.dashboard build` | Generate `PROJECT_STATUS.md`. |
| `python -m automation.rules register` | Register a business rule (`<PREFIX>-BR-NNN`). |
| `python -m automation.rules list` | List registered business rules. |
| `python -m automation adr new "<title>"` | Create next-numbered ADR. |
| `python -m automation adr list` | List ADRs. |
| `python -m automation ai add\|approve\|reject\|list` | Manage the AI documentation archive. |
| `python -m automation health report` | Generate repository health report. |

*End of NDF Technical Architecture Document.*
