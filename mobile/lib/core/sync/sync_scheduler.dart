import 'dart:async';

import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/sync_manager.dart';

/// Drives background synchronization on a fixed cadence. Connectivity-triggered
/// and manual syncs are handled by the [SyncManager] itself; this scheduler adds
/// the periodic heartbeat.
///
/// The timer is lightweight: it simply asks the manager to sync, which is a
/// no-op cheap path when offline or already running.
class SyncScheduler {
  SyncScheduler(
    this._manager, {
    this.interval = const Duration(minutes: 15),
    this.syncOnStart = true,
  });

  final SyncManager _manager;
  final Duration interval;
  final bool syncOnStart;
  final _log = AppLogger.of('SyncScheduler');

  Timer? _timer;
  bool _running = false;

  bool get isRunning => _running;

  void start() {
    if (_running) return;
    _running = true;
    _log.info('Started (every ${interval.inMinutes} min)');
    if (syncOnStart) {
      unawaited(_manager.syncNow(trigger: 'startup'));
    }
    _timer = Timer.periodic(interval, (_) {
      unawaited(_manager.syncNow(trigger: 'scheduled'));
    });
  }

  /// Triggers an immediate sync without disturbing the periodic cadence.
  Future<void> triggerNow() => _manager.syncNow(trigger: 'manual');

  void stop() {
    _timer?.cancel();
    _timer = null;
    _running = false;
    _log.info('Stopped');
  }

  void dispose() => stop();
}
