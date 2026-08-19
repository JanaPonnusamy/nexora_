import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/agent/agent_settings_repository.dart';
import 'package:nexora_mobile/core/agent/backend_health_service.dart';
import 'package:nexora_mobile/core/agent/device_info_service.dart';
import 'package:nexora_mobile/core/agent/store_config_service.dart';
import 'package:nexora_mobile/core/config/app_config.dart';
import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/network/dio_client.dart';
import 'package:nexora_mobile/core/observability/crash_reporter.dart';
import 'package:nexora_mobile/core/security/biometric_service.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';
import 'package:nexora_mobile/core/sync/conflict_handler.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/core/sync/delta_processor.dart';
import 'package:nexora_mobile/core/sync/retry_policy.dart';
import 'package:nexora_mobile/core/sync/sync_logger.dart';
import 'package:nexora_mobile/core/sync/sync_queue.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/data/auth_repository.dart';
import 'package:nexora_mobile/features/master_data/data/category_repository.dart';
import 'package:nexora_mobile/features/master_data/data/department_repository.dart';
import 'package:nexora_mobile/features/master_data/data/manufacturer_repository.dart';
import 'package:nexora_mobile/features/master_data/data/master_data_api_service.dart';
import 'package:nexora_mobile/features/master_data/data/supplier_repository.dart';
import 'package:nexora_mobile/features/master_data/data/tax_rate_repository.dart';
import 'package:nexora_mobile/features/master_data/data/unit_repository.dart';
import 'package:nexora_mobile/features/store_selection/data/store_repository.dart';
import 'package:nexora_mobile/features/sync/data/sync_admin_service.dart';

/// Root dependency-injection graph for the app. Everything is wired through
/// Riverpod providers so construction stays lazy, single-instance and testable
/// (override any provider in tests).

/// Resolved, environment-specific configuration. Overridden in `bootstrap`.
final appConfigProvider = Provider<AppConfig>(
  (ref) => throw UnimplementedError('appConfigProvider must be overridden'),
);

/// Secure storage (Keychain / Keystore) for the JWT and selected store.
final secureStorageProvider = Provider<SecureStorageService>(
  (ref) => SecureStorageService(),
);

/// Platform biometric / device-credential prompt, behind unlock-on-open.
final biometricServiceProvider = Provider<BiometricService>(
  (ref) => BiometricService(),
);

/// Where uncaught errors go. Overridden in `bootstrap` with the instance the
/// crash handlers were installed against, so handler-captured errors and
/// in-app reports land in the same buffer.
final crashReporterProvider = Provider<CrashReporter>(
  (ref) => LoggingCrashReporter(),
);

/// The single shared Dio instance. Its auth interceptor calls back into the
/// [authControllerProvider] to tear the session down on a 401.
final dioProvider = Provider<Dio>((ref) {
  final config = ref.watch(appConfigProvider);
  final storage = ref.watch(secureStorageProvider);
  return DioClient.create(
    config: config,
    storage: storage,
    onUnauthorized: () async {
      await ref.read(authControllerProvider.notifier).onUnauthorized();
    },
  );
});

/// Repositories.
final authRepositoryProvider = Provider<AuthRepository>(
  (ref) => AuthRepository(ref.watch(dioProvider)),
);

final storeRepositoryProvider = Provider<StoreRepository>(
  (ref) => StoreRepository(ref.watch(dioProvider)),
);

// --- Local persistence -------------------------------------------------------

/// The single shared Drift database instance for the whole app.
final appDatabaseProvider = Provider<AppDatabase>((ref) {
  final db = AppDatabase();
  ref.onDispose(db.close);
  return db;
});

/// Narrow persistence gateway for all sync/agent tables.
final syncRepositoryProvider = Provider<SyncRepository>(
  (ref) => SyncRepository(ref.watch(appDatabaseProvider)),
);

// --- Sync engine primitives (Phase 3) ---------------------------------------

/// Backoff policy shared by the queue and network retries.
final retryPolicyProvider = Provider<RetryPolicy>(
  (ref) => const RetryPolicy(),
);

final conflictHandlerProvider = Provider<ConflictHandler>(
  (ref) => const ConflictHandler(),
);

final syncLoggerProvider = Provider<SyncLogger>(
  (ref) => SyncLogger(ref.watch(syncRepositoryProvider)),
);

final syncQueueProvider = Provider<SyncQueue>(
  (ref) => SyncQueue(
    ref.watch(syncRepositoryProvider),
    ref.watch(syncLoggerProvider),
    retryPolicy: ref.watch(retryPolicyProvider),
  ),
);

/// Connectivity monitor (OS network state). Started by the sync manager.
final connectivityServiceProvider = Provider<ConnectivityService>((ref) {
  final service = ConnectivityService();
  ref.onDispose(service.dispose);
  return service;
});

/// Reactive network status for widgets.
///
/// [ConnectivityService.statusStream] carries *transitions* only — it emits
/// when the status changes, not what it currently is. A widget watching it
/// alone would show nothing on a phone that has been offline since launch,
/// because from its point of view nothing has happened. So the current status
/// is probed and yielded first, and the transitions follow.
final networkStatusProvider = StreamProvider<NetworkStatus>((ref) async* {
  final service = ref.watch(connectivityServiceProvider);
  yield await service.check();
  yield* service.statusStream;
});

/// Plain boolean form, for widgets that only need "can I reach anything".
///
/// Optimistic while the first probe is in flight: a banner that flashes
/// "offline" for 200ms on every cold start is noise, and the cost of being a
/// moment late is nothing.
final isOnlineProvider = Provider<bool>((ref) {
  return ref.watch(networkStatusProvider).maybeWhen(
        data: (status) => status.isOnline,
        orElse: () => true,
      );
});

/// Delta dispatch coordinator; concrete entity processors are registered by the
/// agent manager at bootstrap.
final deltaProcessorProvider = Provider<DeltaProcessor>(
  (ref) => DeltaProcessor(
    ref.watch(syncRepositoryProvider),
    ref.watch(syncLoggerProvider),
  ),
);

// --- Store agent services (Phase 2) -----------------------------------------

final deviceInfoServiceProvider = Provider<DeviceInfoService>(
  (ref) => DeviceInfoService(
    ref.watch(syncRepositoryProvider),
    ref.watch(secureStorageProvider),
  ),
);

final backendHealthServiceProvider = Provider<BackendHealthService>(
  (ref) => BackendHealthService(ref.watch(dioProvider)),
);

final storeConfigServiceProvider = Provider<StoreConfigService>(
  (ref) => StoreConfigService(
    ref.watch(storeRepositoryProvider),
    ref.watch(syncRepositoryProvider),
    conflictHandler: ref.watch(conflictHandlerProvider),
  ),
);

final agentSettingsRepositoryProvider = Provider<AgentSettingsRepository>(
  (ref) => AgentSettingsRepository(ref.watch(syncRepositoryProvider)),
);

// --- Master data (Phase 4) ---------------------------------------------------

/// Shared network access for master-data entities (only Suppliers is wired to a
/// real endpoint; see docs/API_CONTRACT.md).
final masterDataApiServiceProvider = Provider<MasterDataApiService>(
  (ref) => MasterDataApiService(ref.watch(dioProvider)),
);

/// Offline, Drift-only master-data repositories. UI reads these; sync writes
/// these. None require the network.
final departmentRepositoryProvider = Provider<DepartmentRepository>(
  (ref) => DepartmentRepository(
    ref.watch(appDatabaseProvider),
    ref.watch(conflictHandlerProvider),
  ),
);

final categoryRepositoryProvider = Provider<CategoryRepository>(
  (ref) => CategoryRepository(
    ref.watch(appDatabaseProvider),
    ref.watch(conflictHandlerProvider),
  ),
);

final manufacturerRepositoryProvider = Provider<ManufacturerRepository>(
  (ref) => ManufacturerRepository(
    ref.watch(appDatabaseProvider),
    ref.watch(conflictHandlerProvider),
  ),
);

final unitRepositoryProvider = Provider<UnitRepository>(
  (ref) => UnitRepository(
    ref.watch(appDatabaseProvider),
    ref.watch(conflictHandlerProvider),
  ),
);

final taxRateRepositoryProvider = Provider<TaxRateRepository>(
  (ref) => TaxRateRepository(
    ref.watch(appDatabaseProvider),
    ref.watch(conflictHandlerProvider),
  ),
);

final supplierRepositoryProvider = Provider<SupplierRepository>(
  (ref) => SupplierRepository(
    ref.watch(appDatabaseProvider),
    ref.watch(conflictHandlerProvider),
  ),
);

// --- Sync administration (network-wide, read-only) --------------------------

final syncAdminServiceProvider = Provider<SyncAdminService>(
  (ref) => SyncAdminService(ref.watch(dioProvider)),
);
