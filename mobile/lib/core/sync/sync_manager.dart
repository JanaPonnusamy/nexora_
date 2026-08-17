import 'dart:async';

import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/core/sync/delta_processor.dart';
import 'package:nexora_mobile/core/sync/sync_events.dart';
import 'package:nexora_mobile/core/sync/sync_logger.dart';
import 'package:nexora_mobile/core/sync/sync_queue.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';
import 'package:nexora_mobile/core/sync/sync_state.dart';
import 'package:nexora_mobile/core/sync/sync_status.dart';

/// Heart of the offline sync engine. Owns the [SyncState], drives sync cycles,
/// reacts to connectivity, applies retry via the [SyncQueue], and persists
/// enough to resume after an interruption.
///
/// It is transport-agnostic: what actually gets synced is decided by the
/// [EntityDeltaProcessor]s registered on the [DeltaProcessor].
class SyncManager {
  SyncManager({
    required SyncQueue queue,
    required DeltaProcessor deltaProcessor,
    required ConnectivityService connectivity,
    required SyncRepository repository,
    required SyncLogger logger,
  })  : _queue = queue,
        _delta = deltaProcessor,
        _connectivity = connectivity,
        _repo = repository,
        _logger = logger;

  final SyncQueue _queue;
  final DeltaProcessor _delta;
  final ConnectivityService _connectivity;
  final SyncRepository _repo;
  final SyncLogger _logger;

  final _stateController = StreamController<SyncState>.broadcast();
  final _eventController = StreamController<SyncEvent>.broadcast();
  StreamSubscription<NetworkStatus>? _connSub;

  SyncState _state = const SyncState.initial();
  Future<void>? _inFlight;
  bool _paused = false;
  bool _initialized = false;

  SyncState get state => _state;
  Stream<SyncState> get stateStream => _stateController.stream;
  Stream<SyncEvent> get events => _eventController.stream;
  bool get isPaused => _paused;

  /// Restores persisted state, recovers interrupted work and wires connectivity.
  /// Safe to call once during bootstrap.
  Future<void> initialize() async {
    if (_initialized) return;
    _initialized = true;

    // 1) Recover rows abandoned mid-flight by a previous (killed) run.
    final recovered = await _queue.recoverInterrupted();
    if (recovered > 0) {
      await _logger.warning(
        'Recovered $recovered interrupted queue item(s)',
        category: 'startup',
      );
    }

    // 2) Restore the last known engine state (for display continuity).
    final persisted = await _repo.readState();
    final pending = await _queue.pendingCount();
    _emit(
      _state.copyWith(
        status: SyncStatus.idle,
        pending: pending,
        lastRunAt: persisted?.lastRunAt,
        lastSuccessAt: persisted?.lastSuccessAt,
        lastError: persisted?.lastError,
      ),
    );

    // 3) Seed + subscribe to connectivity; a return-to-online triggers a sync.
    await _connectivity.start();
    _setOnline(_connectivity.lastKnown.isOnline);
    _connSub = _connectivity.statusStream.listen((status) {
      final online = status.isOnline;
      _setOnline(online);
      _eventController.add(SyncConnectivityChanged(online: online));
      if (online && !_paused) {
        // Automatic reconnect + resume.
        unawaited(syncNow(trigger: 'connectivity'));
      }
    });
  }

  /// Registers a processor and ensures its entity has a metadata row.
  void register(EntityDeltaProcessor processor) => _delta.register(processor);

  void pause() {
    _paused = true;
    _emit(_state.copyWith(status: SyncStatus.paused));
    unawaited(_persist(SyncStatus.paused));
  }

  void resume() {
    _paused = false;
    unawaited(syncNow(trigger: 'resume'));
  }

  /// Runs (or joins) a single sync cycle. Concurrent callers await the same run.
  Future<void> syncNow({String trigger = 'manual'}) {
    if (_inFlight != null) return _inFlight!;
    final run = _runCycle(trigger).whenComplete(() => _inFlight = null);
    _inFlight = run;
    return run;
  }

  Future<void> _runCycle(String trigger) async {
    if (_paused) return;

    if (!_connectivity.lastKnown.isOnline) {
      final pending = await _queue.pendingCount();
      _emit(
        _state.copyWith(
          status: SyncStatus.offline,
          online: false,
          pending: pending,
          progress: 0,
        ),
      );
      await _logger.info(
        'Offline — deferring sync (pending: $pending)',
        category: 'connectivity',
      );
      await _persist(SyncStatus.offline);
      return;
    }

    _eventController.add(SyncCycleStarted(trigger: trigger));
    _emit(
      _state.copyWith(
        status: SyncStatus.connecting,
        online: true,
        progress: 0,
        completed: 0,
        failed: 0,
        clearError: true,
      ),
    );

    var completed = 0;
    var failed = 0;

    try {
      // Ensure a fresh pull is queued for every registered entity.
      for (final entity in _delta.entities) {
        await _queue.enqueuePullOnce(entity);
      }

      _emit(_state.copyWith(status: SyncStatus.syncing));

      // Drain until no immediately-eligible rows remain (retry rows with a
      // future backoff are intentionally left for a later cycle).
      while (true) {
        final batch = await _queue.claim(limit: 20);
        if (batch.isEmpty) break;

        for (final item in batch) {
          _emit(_state.copyWith(currentEntity: item.entity));
          _eventController.add(SyncEntityStarted(item.entity));
          try {
            final result = await _delta.process(item);
            await _queue.complete(item);
            completed++;
            _eventController
                .add(SyncEntityCompleted(item.entity, changed: result.changed));
          } catch (e) {
            final willRetry = await _queue.fail(item, e);
            if (!willRetry) {
              failed++;
              await _delta.markFailed(item.entity, e);
            }
          }

          final pending = await _queue.pendingCount();
          final total = completed + failed + pending;
          final progress = total == 0 ? 1.0 : completed / total;
          _emit(
            _state.copyWith(
              completed: completed,
              failed: failed,
              pending: pending,
              progress: progress.clamp(0.0, 1.0),
            ),
          );
          _eventController.add(SyncProgress(progress.clamp(0.0, 1.0)));
        }
      }

      final pending = await _queue.pendingCount();
      final now = DateTime.now();
      final status = failed > 0 ? SyncStatus.failed : SyncStatus.success;
      _emit(
        _state.copyWith(
          status: status,
          pending: pending,
          completed: completed,
          failed: failed,
          progress: 1.0,
          currentEntity: null,
          clearCurrentEntity: true,
          lastRunAt: now,
          lastSuccessAt: failed == 0 ? now : _state.lastSuccessAt,
          lastError: failed > 0 ? 'One or more items failed' : null,
          clearError: failed == 0,
        ),
      );
      await _persist(status);
      await _logger.info(
        'Cycle done ($trigger): $completed ok, $failed failed, $pending pending',
        category: 'sync',
      );
      _eventController.add(SyncCycleCompleted(_state));
      await _queue.clearCompleted();
    } catch (e, st) {
      _emit(
        _state.copyWith(
          status: SyncStatus.failed,
          lastError: e.toString(),
          currentEntity: null,
          clearCurrentEntity: true,
        ),
      );
      await _persist(SyncStatus.failed, error: e.toString());
      await _logger.error(
        'Cycle aborted: $e',
        category: 'sync',
        detail: st.toString(),
      );
      _eventController.add(SyncCycleFailed(e.toString()));
    }
  }

  void _setOnline(bool online) {
    if (_state.online == online) return;
    _emit(
      _state.copyWith(
        online: online,
        status: online ? _state.status : SyncStatus.offline,
      ),
    );
  }

  void _emit(SyncState next) {
    _state = next;
    if (!_stateController.isClosed) _stateController.add(next);
  }

  Future<void> _persist(SyncStatus status, {String? error}) => _repo.writeState(
        status: status.name,
        lastRunAt: _state.lastRunAt,
        lastSuccessAt: _state.lastSuccessAt,
        lastError: error ?? _state.lastError,
        clearError: error == null && _state.lastError == null,
        pendingCount: _state.pending,
      );

  Future<void> dispose() async {
    await _connSub?.cancel();
    await _stateController.close();
    await _eventController.close();
  }
}
