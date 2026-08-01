# Nexora Mobile (Flutter)

An **additional** frontend for the existing Nexora platform. It consumes the
existing FastAPI backend — it does **not** replace or modify the backend or the
React/desktop clients. The backend remains the single source of truth.

> **Phase 1 scope only:** project scaffold, theme, routing, API client, auth
> foundation, secure token storage, environment config, logging, login screen,
> and store selection. No business modules (inventory, procurement, CRM, HR,
> education, sync) are implemented yet.

---

## Prerequisites

- Flutter **stable** (≥ 3.27) and Dart (≥ 3.6) — `flutter --version`
- The Nexora backend running and reachable (default dev: `http://localhost:8000`)

> ⚠️ This repo was scaffolded without the Flutter SDK present, so the native
> `android/` and `ios/` platform folders and the generated code are **not**
> committed. Run the two steps below once to produce them.

## First-time setup

```bash
cd E:\Nexora\mobile

# 1. Generate the native platform folders (android/, ios/, etc.).
#    `flutter create` will NOT overwrite the existing pubspec.yaml or lib/.
flutter create . --org com.nexora --project-name nexora_mobile \
  --platforms=android,ios,web

# 2. Fetch dependencies.
flutter pub get

# 3. Generate Freezed / json_serializable / Drift / Riverpod code.
#    (Required before the app compiles — *.freezed.dart / *.g.dart are gitignored.)
dart run build_runner build --delete-conflicting-outputs
```

## Running

The backend host differs by target. Point the app at it with a `--dart-define`:

```bash
# Android emulator (host localhost is 10.0.2.2 — this is the default):
flutter run

# iOS simulator (can use localhost directly):
flutter run --dart-define=NEXORA_API_BASE_URL=http://localhost:8000

# Physical device on the LAN (use the HO machine's IP):
flutter run --dart-define=NEXORA_API_BASE_URL=http://192.168.1.50:8000

# Choose an environment (dev | staging | prod):
flutter run --dart-define=NEXORA_ENV=staging
```

## Regenerating code after model changes

```bash
dart run build_runner watch --delete-conflicting-outputs
```

## Architecture

Feature-first, with a shared `core/` for infrastructure:

- **DI:** Riverpod providers (`core/di/providers.dart`) — single Dio, single
  secure-storage, repositories, and the auth controller.
- **Networking:** Dio + interceptors (auth bearer injection, 401 → logout,
  request logging). Errors normalised to `ApiException`.
- **Routing:** GoRouter with an auth-state-driven redirect guard
  (`splash → login → store-selection → dashboard`).
- **State:** `AuthController` (Riverpod `Notifier`) owns the session lifecycle.
- **Persistence:** JWT + selected store in Flutter Secure Storage; a minimal
  Drift database is wired as the foundation for Phase 2 offline sync.

See [docs/API_CONTRACT.md](docs/API_CONTRACT.md) for the exact backend
endpoints consumed and the ones still missing for later phases.
