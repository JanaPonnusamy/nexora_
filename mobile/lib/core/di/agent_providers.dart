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

/// Providers that compose the sync engine + store agent and that depend on the
/// authenticated session. Kept separate from `providers.dart` so the base
/// dependency graph does not need to know about the auth controller.

/// Concrete entity processors registered with the sync engine.
final deltaProcessorsProvider = Provider<List<EntityDeltaProcessor>>((ref) {
  String? currentStoreId() =>
      ref.read(authControllerProvider).selectedStore?.storeId;
  bool isAuthenticated() => ref.read(authControllerProvider).isAuthenticated;

  return [
    StoreConfigDeltaProcessor(
      ref.watch(storeConfigServiceProvider),
      currentStoreId,
    ),
    SessionProfileDeltaProcessor(
      ref.watch(authRepositoryProvider),
      ref.watch(syncRepositoryProvider),
      isAuthenticated,
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

extension<T> on Stream<T> {
  /// Emits [initial] immediately, then forwards every subsequent event. Avoids
  /// a dependency on rxdart for this one convenience.
  Stream<T> startWith(T initial) async* {
    yield initial;
    yield* this;
  }
}
