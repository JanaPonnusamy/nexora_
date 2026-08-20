/// High-level lifecycle status of the sync engine, surfaced on the Sync Status
/// screen and persisted (as its [name]) in the `sync_state` table so it can be
/// restored after a restart.
enum SyncStatus {
  /// Nothing running; the engine is ready.
  idle,

  /// Establishing connectivity / claiming work.
  connecting,

  /// Actively pulling deltas or draining the queue.
  syncing,

  /// Last cycle completed with no failures.
  success,

  /// Last cycle finished with one or more failures (some rows may be retrying).
  failed,

  /// No usable network; work is deferred to the offline queue.
  offline,

  /// Paused by the user or by a control signal.
  paused,
}

extension SyncStatusX on SyncStatus {
  String get label => switch (this) {
        SyncStatus.idle => 'Idle',
        SyncStatus.connecting => 'Connecting',
        SyncStatus.syncing => 'Syncing',
        SyncStatus.success => 'Up to date',
        SyncStatus.failed => 'Needs attention',
        SyncStatus.offline => 'Offline',
        SyncStatus.paused => 'Paused',
      };

  bool get isBusy =>
      this == SyncStatus.connecting || this == SyncStatus.syncing;

  static SyncStatus parse(String? value) => SyncStatus.values.firstWhere(
        (s) => s.name == value,
        orElse: () => SyncStatus.idle,
      );
}
