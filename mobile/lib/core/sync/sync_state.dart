import 'package:nexora_mobile/core/sync/sync_status.dart';

/// Immutable snapshot of the sync engine, exposed to the UI and mirrored into
/// the `sync_state` table for restart recovery.
class SyncState {
  const SyncState({
    this.status = SyncStatus.idle,
    this.online = true,
    this.progress = 0,
    this.pending = 0,
    this.completed = 0,
    this.failed = 0,
    this.currentEntity,
    this.lastRunAt,
    this.lastSuccessAt,
    this.lastError,
  });

  const SyncState.initial() : this();

  final SyncStatus status;
  final bool online;

  /// 0.0–1.0 for the current cycle; 0 when idle.
  final double progress;

  final int pending;
  final int completed;
  final int failed;
  final String? currentEntity;
  final DateTime? lastRunAt;
  final DateTime? lastSuccessAt;
  final String? lastError;

  bool get hasPending => pending > 0;
  bool get isHealthy => status != SyncStatus.failed && failed == 0;

  SyncState copyWith({
    SyncStatus? status,
    bool? online,
    double? progress,
    int? pending,
    int? completed,
    int? failed,
    String? currentEntity,
    bool clearCurrentEntity = false,
    DateTime? lastRunAt,
    DateTime? lastSuccessAt,
    String? lastError,
    bool clearError = false,
  }) {
    return SyncState(
      status: status ?? this.status,
      online: online ?? this.online,
      progress: progress ?? this.progress,
      pending: pending ?? this.pending,
      completed: completed ?? this.completed,
      failed: failed ?? this.failed,
      currentEntity:
          clearCurrentEntity ? null : (currentEntity ?? this.currentEntity),
      lastRunAt: lastRunAt ?? this.lastRunAt,
      lastSuccessAt: lastSuccessAt ?? this.lastSuccessAt,
      lastError: clearError ? null : (lastError ?? this.lastError),
    );
  }

  @override
  String toString() =>
      'SyncState(${status.name}, online=$online, pending=$pending, '
      'completed=$completed, failed=$failed)';
}
