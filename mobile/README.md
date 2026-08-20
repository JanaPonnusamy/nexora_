# Nexora Mobile (Flutter)

This is the **mobile-first Nexora application**.

For current product work, we should focus on the `mobile/` app only and avoid
designing from the web app first. The goal is a clean, modern mobile
experience built from small reusable components.

## Product direction

The mobile app should be treated as its own product surface:

- mobile-first, not web-first
- compact layouts, not desktop tables
- small components, clear actions, clean hierarchy
- feature-by-feature delivery

## Build order

### 1. Sync first

The first polished flow should be the **Sync** area.

Current mobile flow:

- splash
- login
- store selection
- dashboard
- sync status
- device status
- configuration status
- agent settings

This already exists in code and is the right foundation to refine first.

Relevant code areas:

- `lib/features/sync/`
- `lib/features/agent/`
- `lib/core/sync/`
- `lib/core/router/`

### 2. Legacy Order next

After the Sync experience is clean and stable, the next feature to build is the
**Legacy Order** page.

That page should be added later as a dedicated mobile feature, one screen at a
time, instead of trying to bring every old module into the app at once.

## What the mobile app is already doing

This project is not empty. It already includes:

- Flutter app bootstrap
- app theme and routing
- auth flow
- store selection
- dashboard shell
- sync engine foundation
- sync status UI
- device/configuration/agent status UI
- local persistence and API networking foundation

## UI direction

For upcoming mobile work, keep these rules:

- use short screens with strong visual hierarchy
- prefer cards, tiles, pills, and section actions
- keep one primary action per section
- make sync information readable at a glance
- avoid dense web-style layouts
- add modules one by one, starting with Sync

## Prerequisites

- Flutter stable (>= 3.27) and Dart (>= 3.6)
- Nexora backend running and reachable

## First-time setup

```bash
cd E:\Nexora\mobile
flutter pub get
dart run build_runner build --delete-conflicting-outputs
```

If native platform files are missing on a new machine, generate them once:

```bash
flutter create . --org com.nexora --project-name nexora_mobile --platforms=android,ios,web
```

## Running

```bash
flutter run
```

Examples:

```bash
flutter run --dart-define=NEXORA_API_BASE_URL=http://122.252.246.181:8443
flutter run --dart-define=NEXORA_API_BASE_URL=http://192.168.1.50:8000
flutter run --dart-define=NEXORA_ENV=staging
```

## Architecture

Feature-first, with shared infrastructure in `core/`.

- DI: Riverpod providers for shared services and controllers
- Networking: Dio with auth and logging interceptors
- Routing: GoRouter with auth/store guarded flow plus Sync/Agent routes
- State: Riverpod notifiers for session and feature state
- Persistence: secure storage plus Drift for local sync data

See [docs/API_CONTRACT.md](E:\Nexora\mobile\docs\API_CONTRACT.md) for backend
contracts used by the mobile app.
