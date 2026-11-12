# 15 — Watchdog Rebranding Dependency Map
**NEXORA MEDIQ — Phase 1 Baseline Stabilization**

## Correction to Phase 0: the Watchdog's source is in this repository

Phase 0 treated `NexoraStockClientWatchdog` as possibly external and unverifiable. It is not — its source lives at `store_agent_setup/stock_client_watchdog_service.py`, and this phase read it directly.

## What the Watchdog actually depends on (concrete, not inferred)

| Identifier | Current value | Location |
|---|---|---|
| State directory | `PROGRAMDATA\Axythic\StockClient` | `stock_client_watchdog_service.py:74` — `STATE_DIR = PROGRAMDATA / "Axythic" / "StockClient"` |
| Staged/backup/rollback installer filename pattern | `Axythic-Supplier-Stock-Setup-{version}.exe` | `stock_client_watchdog_service.py:456, 517-518, 524, 588` — including `BACKUP_DIR.glob("Axythic-Supplier-Stock-Setup-*.exe")` for rollback candidate discovery |
| Prose references | `"Axythic Supplier Stock"` | `stock_client_watchdog_service.py:3` (docstring), `622` (docstring) — cosmetic, not functional, but confirms the name is baked into log/comment text too |
| `appId` | `com.nexora.desktop.stock` | `desktop/supplier-stock-client/package.json:25` |
| `productName` | `Axythic Supplier Stock` | `package.json:26` |
| Installer artifact name template | `Axythic-Supplier-Stock-Setup-${version}.${ext}` | `package.json:13` (`dist` script's `--config.artifactName`) |
| Update feed URL | `http://192.168.10.80:8000/updates` | `package.json:45-48` (`publish`) — **vestigial**, not actually used (see below) |
| Window title | `Axythic Supplier Stock` | `main.cjs:238` |
| In-app document title | `` `Axythic Supplier Stock · ${storeName}` `` | `App.jsx:531` |
| In-app logo alt/header text | `"Axythic"` | `App.jsx:659, 661` |
| In-app copy | "Axythic API" / "Axythic desktop" / "Axythic credentials" | `App.jsx:1229, 1556, 1558` |

## Confirmation: Electron's own auto-updater is a confirmed no-op, by design

`main.cjs:297-309` — `initAutoUpdates()` is intentionally a no-op. Full reasoning transcribed from the in-code comment: a running application cannot safely replace its own files while executing, so update delivery is owned entirely by the separate SYSTEM-level Watchdog service, which performs HO-authorized version polling, SHA-256 + Ed25519 package signature verification, a GUI-close → install → health-check → rollback-on-failure sequence. **This means `package.json`'s `publish`/update-feed block is dead configuration** — changing it has no effect on real update behavior, and leaving it as-is during a rebrand carries no functional risk (only cosmetic inconsistency if left un-updated).

## What actually breaks if the rebrand is done carelessly

The Watchdog's rollback/staging logic uses `glob("Axythic-Supplier-Stock-Setup-*.exe")` to find installer packages. **If `package.json`'s `artifactName` template changes without the Watchdog's glob pattern changing in lockstep, the Watchdog will stop finding, staging, or rolling back new installer packages on every store PC running it.** This is a concrete, mechanical break — not a hypothetical risk — because the matching is literal filename substring matching, not semantic.

## Required coordinated change set (for Phase 3, not this phase)

All of the following must change together, in one coordinated release, not independently:
1. `package.json` — `appId`, `productName`, `artifactName` template.
2. `main.cjs` — window title string (line 238).
3. `App.jsx` — document title template (531), logo alt/header text (659, 661), in-app copy (1229, 1556, 1558).
4. `stock_client_watchdog_service.py` — the hardcoded filename-pattern glob (456, 517-518, 524, 588) and ideally the `STATE_DIR` folder name (74) and docstring text (3, 622), though the state-directory folder name change needs its own migration consideration (existing installs already have data under the old path — a path rename requires either a one-time migration step in the Watchdog or support for both the old and new path during a transition window).
5. Logo asset file itself (`src/assets/axythic-logo-mark.png` → new NEXORA MEDIQ mark).

## Open item not resolved in this phase

How the Watchdog service itself gets updated on store PCs (i.e., its own deployment/release mechanism, separate from the app it watches) was not traced in this pass. Before Phase 3 rebranding executes, confirm how a new version of `stock_client_watchdog_service.py` reaches already-deployed store PCs — if that path is slow or manual, the coordinated change set above may need a transition period where both old and new filename patterns are recognized, rather than a hard cutover.

## Verdict

**Rebranding is fully mappable and coordinatable — not an unknown-risk area anymore.** Phase 0's "coordinate with whoever owns the Watchdog" caution was reasonable given incomplete information at the time; this phase found the Watchdog is part of this same repository and its exact dependencies are now enumerated above. Phase 3 should treat items 1-5 as one atomic change, and should resolve the open item (Watchdog's own update path) before executing.
