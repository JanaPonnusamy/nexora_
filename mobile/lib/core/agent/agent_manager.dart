import 'dart:async';

import 'package:nexora_mobile/core/agent/agent_settings.dart';
import 'package:nexora_mobile/core/agent/agent_settings_repository.dart';
import 'package:nexora_mobile/core/agent/agent_state.dart';
import 'package:nexora_mobile/core/agent/agent_status.dart';
import 'package:nexora_mobile/core/agent/backend_health_service.dart';
import 'package:nexora_mobile/core/agent/device_info_service.dart';
import 'package:nexora_mobile/core/agent/store_config_service.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/core/sync/delta_processor.dart';
import 'package:nexora_mobile/core/sync/sync_manager.dart';
import 'package:nexora_mobile/core/sync/sync_scheduler.dart';

/// The Legacy Store Agent runtime.
///
/// Coordinates the whole Phase-2 startup/bootstrap flow — device registration
/// (local), configuration download + cache, backend health / API-version
/// checks — and owns the periodic health monitor and the sync scheduler
/// (Phase 3). Everything degrades gracefully offline using cached data.
class AgentManager {
  AgentManager({
    required DeviceInfoService deviceInfo,
    required StoreConfigService storeConfig,
    required BackendHealthService health,
    required AgentSettingsRepository settingsRepository,
    required SyncManager syncManager,
    required ConnectivityService connectivity,
    required List<EntityDeltaProcessor> processors,
    required String? Function() currentStoreId,
    required String? Function() currentStoreName,
  })  : _deviceInfo = deviceInfo,
        _storeConfig = storeConfig,
        _health = health,
        _settingsRepo = settingsRepository,
        _sync = syncManager,
        _connectivity = connectivity,
        _processors = processors,
        _currentStoreId = currentStoreId,
        _currentStoreName = currentStoreName;

  final DeviceInfoService _deviceInfo;
  final StoreConfigService _storeConfig;
  final BackendHealthService _health;
  final AgentSettingsRepository _settingsRepo;
  final SyncManager _sync;
  final ConnectivityService _connectivity;
  final List<EntityDeltaProcessor> _processors;
  final String? Function() _currentStoreId;
  final String? Function() _currentStoreName;

  final _log = AppLogger.of('AgentManager');
  final _stateController = StreamController<AgentState>.broadcast();

  AgentState _state = const AgentState.initial();
  AgentSettings _settings = AgentSettings.defaults;
  SyncScheduler? _scheduler;
  Timer? _healthTimer;
  bool _initialized = false;

  AgentState get state => _state;
  AgentSettings get settings => _settings;
  Stream<AgentState> get stateStream => _stateController.stream;
  SyncManager get syncManager => _sync;

  /// Full bootstrap. Idempotent; safe to call once after auth is ready.
  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;
    _log.info('Bootstrapping store agent');

    try {
      // 1) Settings first (drive intervals).
      _settings = await _settingsRepo.load();

      // 2) Local device registration.
      _emit(_state.copyWith(status: AgentStatus.registering));
      final device = await _deviceInfo.registerOrRefresh();
      _emit(_state.copyWith(deviceId: device.deviceId, registered: true));

      // 3) Register sync entities + start the sync engine.
      for (final p in _processors) {
        _sync.register(p);
      }
      await _sync.initialize();

      // 4) First health probe (best-effort).
      await _runHealthCheck();

      // 5) Configuration download / cache.
      _emit(_state.copyWith(
        status: AgentStatus.downloadingConfig,
        storeName: _currentStoreName(),
      ),);
      await _loadConfiguration();

      // 6) Start periodic health monitor + scheduled sync.
      _startHealthMonitor();
      _startScheduler();

      _emit(_state.copyWith(status: _deriveStatus()));
      _log.info('Store agent ready (${_state.status.name})');
    } catch (e, st) {
      _log.severe('Agent bootstrap failed: $e', e, st);
      _emit(_state.copyWith(
        status: AgentStatus.error,
        lastError: e.toString(),
      ),);
    }
  }

  /// Manual "refresh configuration" — re-probes health, re-downloads config and
  /// kicks a sync cycle.
  Future<void> refreshConfiguration() async {
    await _runHealthCheck();
    await _loadConfiguration();
    await _sync.syncNow(trigger: 'manual');
    _emit(_state.copyWith(status: _deriveStatus()));
  }

  /// Manual sync trigger for the Sync Status screen.
  Future<void> triggerSync() => _sync.syncNow(trigger: 'manual');

  /// Apply new settings, persist them, and reconfigure timers.
  Future<void> updateSettings(AgentSettings next) async {
    _settings = next;
    await _settingsRepo.save(next);
    _startHealthMonitor(); // re-arms with new interval
    _startScheduler(); // re-arms with new interval / autoSync
    _log.info('Applied new agent settings');
  }

  Future<void> _loadConfiguration() async {
    final storeId = _currentStoreId();
    if (storeId == null || storeId.isEmpty) {
      _emit(_state.copyWith(clearError: true));
      return;
    }

    // Prefer a fresh download; fall back to cache when offline/unreachable.
    if (_state.backendReachable) {
      try {
        final store = await _storeConfig.download(storeId);
        if (store != null) {
          _emit(_state.copyWith(
            configLoaded: true,
            storeName: store.storeName,
            lastConfigSyncAt: DateTime.now(),
            clearError: true,
          ),);
          return;
        }
      } catch (e) {
        _log.warning('Config download failed, will use cache: $e');
      }
    }

    final cached = await _storeConfig.readCached();
    _emit(_state.copyWith(
      configLoaded: cached != null,
      storeName: cached?.store.storeName ?? _currentStoreName(),
    ),);
  }

  Future<void> _runHealthCheck() async {
    final result = await _health.check();
    _emit(_state.copyWith(
      backendReachable: result.reachable,
      apiCompatible: result.apiCompatible,
      backendLatencyMs: result.latencyMs,
      clearLatency: result.latencyMs == null,
      serverApiVersion: result.serverApiVersion,
      lastHealthCheckAt: result.checkedAt,
      status: _deriveStatus(reachable: result.reachable),
    ),);
    await _deviceInfo.touch();
  }

  void _startHealthMonitor() {
    _healthTimer?.cancel();
    _healthTimer = Timer.periodic(_settings.healthCheckInterval, (_) {
      unawaited(_runHealthCheck());
    });
  }

  void _startScheduler() {
    _scheduler?.stop();
    if (!_settings.autoSync) {
      _scheduler = null;
      return;
    }
    _scheduler = SyncScheduler(
      _sync,
      interval: _settings.syncInterval,
      syncOnStart: _settings.syncOnStartup,
    )..start();
  }

  AgentStatus _deriveStatus({bool? reachable}) {
    final isReachable = reachable ?? _state.backendReachable;
    if (!_connectivity.lastKnown.isOnline) return AgentStatus.offline;
    if (isReachable) return AgentStatus.ready;
    // Network up but backend unreachable → degraded if we have cached config.
    return _state.configLoaded ? AgentStatus.degraded : AgentStatus.offline;
  }

  void _emit(AgentState next) {
    _state = next;
    if (!_stateController.isClosed) _stateController.add(next);
  }

  Future<void> dispose() async {
    _healthTimer?.cancel();
    _scheduler?.dispose();
    await _stateController.close();
  }
}
