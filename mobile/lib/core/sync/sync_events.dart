import 'package:nexora_mobile/core/sync/sync_state.dart';

/// Events emitted by the [SyncManager] over its broadcast stream. UI and tests
/// can react to discrete transitions without polling the aggregate state.
sealed class SyncEvent {
  SyncEvent() : at = DateTime.now();
  final DateTime at;
}

/// A full sync cycle began.
class SyncCycleStarted extends SyncEvent {
  SyncCycleStarted({required this.trigger});

  /// What kicked the cycle: `manual`, `scheduled`, `connectivity`, `startup`.
  final String trigger;
}

/// Work on a single entity began.
class SyncEntityStarted extends SyncEvent {
  SyncEntityStarted(this.entity);
  final String entity;
}

/// Work on a single entity finished.
class SyncEntityCompleted extends SyncEvent {
  SyncEntityCompleted(this.entity, {required this.changed});
  final String entity;
  final int changed;
}

/// Aggregate progress ticked.
class SyncProgress extends SyncEvent {
  SyncProgress(this.value);

  /// 0.0–1.0.
  final double value;
}

/// The cycle finished (successfully or with recoverable failures).
class SyncCycleCompleted extends SyncEvent {
  SyncCycleCompleted(this.state);
  final SyncState state;
}

/// The cycle aborted; [error] describes why.
class SyncCycleFailed extends SyncEvent {
  SyncCycleFailed(this.error);
  final String error;
}

/// Connectivity changed while the engine was alive.
class SyncConnectivityChanged extends SyncEvent {
  SyncConnectivityChanged({required this.online});
  final bool online;
}
