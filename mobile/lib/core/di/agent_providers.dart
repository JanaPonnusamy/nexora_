import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/agent/agent_manager.dart';
import 'package:nexora_mobile/core/agent/agent_state.dart';
import 'package:nexora_mobile/core/agent/delta/session_profile_delta_processor.dart';
import 'package:nexora_mobile/core/agent/delta/store_config_delta_processor.dart';
import 'package:nexora_mobile/core/agent/device_info_service.dart';
import 'package:nexora_mobile/core/agent/store_config_service.dart';
import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/sync/delta_processor.dart';
import 'package:nexora_mobile/core/sync/sync_manager.dart';
import 'package:nexora_mobile/core/sync/sync_state.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';
import 'package:nexora_mobile/features/master_data/sync/entity_delta_processors.dart';
import 'package:nexora_mobile/features/sync/data/sync_control_center.dart';

/// Providers that compose the sync engine + store agent and that depend on the
/// authenticated session. Kept separate from `providers.dart` so the base
/// dependency graph does not need to know about the auth controller.

/// Resolves the current tenant/store/user scope from the auth session. Nothing
/// global is assumed — master-data sync and reads are always scoped to this.
final masterScopeProvider = Provider<MasterScope Function()>((ref) {
  return () {
    final auth = ref.read(authControllerProvider);
    final store = auth.selectedStore;
    final tenantId = store?.tenantId ?? auth.user?.tenantId ?? '';
    return MasterScope(
      tenantId: tenantId,
      storeId: store?.storeId,
      userId: auth.user?.userId,
    );
  };
});

/// Concrete entity processors registered with the sync engine.
final deltaProcessorsProvider = Provider<List<EntityDeltaProcessor>>((ref) {
  String? currentStoreId() =>
      ref.read(authControllerProvider).selectedStore?.storeId;
  bool isAuthenticated() => ref.read(authControllerProvider).isAuthenticated;
  final scope = ref.watch(masterScopeProvider);
  final logger = ref.watch(syncLoggerProvider);

  return [
    // Phase 2/3 entities.
    StoreConfigDeltaProcessor(
      ref.watch(storeConfigServiceProvider),
      currentStoreId,
    ),
    SessionProfileDeltaProcessor(
      ref.watch(authRepositoryProvider),
      ref.watch(syncRepositoryProvider),
      isAuthenticated,
    ),
    // Phase 4 business master data.
    SupplierDeltaProcessor(
      repository: ref.watch(supplierRepositoryProvider),
      api: ref.watch(masterDataApiServiceProvider),
      scope: scope,
      logger: logger,
    ),
    DepartmentDeltaProcessor(
      repository: ref.watch(departmentRepositoryProvider),
      scope: scope,
      logger: logger,
    ),
    CategoryDeltaProcessor(
      repository: ref.watch(categoryRepositoryProvider),
      scope: scope,
      logger: logger,
    ),
    ManufacturerDeltaProcessor(
      repository: ref.watch(manufacturerRepositoryProvider),
      scope: scope,
      logger: logger,
    ),
    UnitDeltaProcessor(
      repository: ref.watch(unitRepositoryProvider),
      scope: scope,
      logger: logger,
    ),
    TaxRateDeltaProcessor(
      repository: ref.watch(taxRateRepositoryProvider),
      scope: scope,
      logger: logger,
    ),
  ];
});

/// The Phase-3 sync orchestrator.
final syncManagerProvider = Provider<SyncManager>((ref) {
  final manager = SyncManager(
    queue: ref.watch(syncQueueProvider),
    deltaProcessor: ref.watch(deltaProcessorProvider),
    connectivity: ref.watch(connectivityServiceProvider),
    repository: ref.watch(syncRepositoryProvider),
    logger: ref.watch(syncLoggerProvider),
  );
  ref.onDispose(manager.dispose);
  return manager;
});

/// The Phase-2 store agent runtime.
final agentManagerProvider = Provider<AgentManager>((ref) {
  String? currentStoreId() =>
      ref.read(authControllerProvider).selectedStore?.storeId;
  String? currentStoreName() =>
      ref.read(authControllerProvider).selectedStore?.storeName;

  final manager = AgentManager(
    deviceInfo: ref.watch(deviceInfoServiceProvider),
    storeConfig: ref.watch(storeConfigServiceProvider),
    health: ref.watch(backendHealthServiceProvider),
    settingsRepository: ref.watch(agentSettingsRepositoryProvider),
    syncManager: ref.watch(syncManagerProvider),
    connectivity: ref.watch(connectivityServiceProvider),
    processors: ref.watch(deltaProcessorsProvider),
    currentStoreId: currentStoreId,
    currentStoreName: currentStoreName,
  );
  ref.onDispose(manager.dispose);
  return manager;
});

// --- Reactive views for the UI ----------------------------------------------

/// Live sync state stream (seeded with the manager's current value).
final syncStateProvider = StreamProvider<SyncState>((ref) {
  final manager = ref.watch(syncManagerProvider);
  return manager.stateStream.startWith(manager.state);
});

/// Live agent state stream (seeded with the manager's current value).
final agentStateProvider = StreamProvider<AgentState>((ref) {
  final manager = ref.watch(agentManagerProvider);
  return manager.stateStream.startWith(manager.state);
});

/// Recent sync log entries for the activity feed.
final syncHistoryProvider = StreamProvider<List<SyncHistoryData>>(
  (ref) => ref.watch(syncRepositoryProvider).watchHistory(limit: 60),
);

/// Per-entity sync metadata (watermark, counts, last status).
final syncMetadataProvider = StreamProvider<List<SyncMetadataData>>(
  (ref) => ref.watch(syncRepositoryProvider).watchMetadata(),
);

/// Live queue rows (for the queue view on the Sync Status screen).
final syncQueueRowsProvider = StreamProvider<List<SyncQueueData>>(
  (ref) => ref.watch(syncRepositoryProvider).watchQueue(),
);

/// The cached store configuration.
final cachedStoreConfigProvider = StreamProvider<CachedStoreConfig?>(
  (ref) => ref.watch(storeConfigServiceProvider).watchCached(),
);

/// Cached device identity (survives offline; loaded from the local DB).
final cachedDeviceProvider = FutureProvider<DeviceIdentity?>(
  (ref) => ref.watch(deviceInfoServiceProvider).cached(),
);

/// All cached configuration entries (for the Configuration Status screen).
final allConfigProvider = FutureProvider<List<SyncConfigurationData>>(
  (ref) => ref.watch(syncRepositoryProvider).allConfig(),
);

/// Network-wide Sync Control Center data (KPIs + every store's live status).
///
/// `GET /api/sync/control-center` is not tenant-scoped server-side, so this is
/// only ever watched from a spot gated on `isPlatformUser` — see
/// `isPlatformUserProvider` and the Sync Status screen. `autoDispose` keeps it
/// from polling while nobody is looking at the screen.
final syncControlCenterProvider =
    FutureProvider.autoDispose<SyncControlCenter>((ref) {
  return ref.watch(syncAdminServiceProvider).fetchControlCenter();
});

/// Whether the current session may see network-wide (cross-store) sync data.
final isPlatformUserProvider = Provider<bool>(
  (ref) => ref.watch(authControllerProvider).user?.isPlatformUser ?? false,
);

extension<T> on Stream<T> {
  /// Emits [initial] immediately, then forwards every subsequent event. Avoids
  /// a dependency on rxdart for this one convenience.
  Stream<T> startWith(T initial) async* {
    yield initial;
    yield* this;
  }
}
