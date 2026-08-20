import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/sync/retry_policy.dart';
import 'package:nexora_mobile/core/sync/sync_logger.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';

/// Direction of a queued operation.
enum SyncDirection { download, upload }

/// Lifecycle of a queued row. The four "logical queues" the spec calls for are
/// views over these values + [SyncDirection]:
///   * upload queue    → direction == upload, status pending/inFlight
///   * download queue  → direction == download, status pending/inFlight
///   * retry queue     → status == pending AND attempts > 0
///   * offline queue   → everything still pending while the device is offline
enum QueueItemStatus { pending, inFlight, done, deadLetter }

extension QueueItemStatusX on QueueItemStatus {
  static QueueItemStatus parse(String v) => QueueItemStatus.values
      .firstWhere((s) => s.name == v, orElse: () => QueueItemStatus.pending);
}

/// Durable operation queue. Wraps [SyncRepository] with retry/backoff semantics
/// so the [SyncManager] can enqueue, claim, complete and fail work without
/// touching Drift directly. All state is persisted, so the queue survives
/// restarts and interrupted runs.
class SyncQueue {
  SyncQueue(this._repo, this._logger, {RetryPolicy? retryPolicy})
      : _retry = retryPolicy ?? const RetryPolicy();

  final SyncRepository _repo;
  final SyncLogger _logger;
  final RetryPolicy _retry;

  RetryPolicy get retryPolicy => _retry;

  Future<int> enqueue({
    required SyncDirection direction,
    required String entity,
    required String operation,
    String payload = '{}',
  }) async {
    final id = await _repo.enqueue(
      direction: direction.name,
      entity: entity,
      operation: operation,
      payload: payload,
      maxAttempts: _retry.maxAttempts,
    );
    await _logger.fine(
      'Enqueued $operation $entity (#$id)',
      category: 'queue',
      entity: entity,
    );
    return id;
  }

  /// Ensures exactly one pending download exists for [entity] (avoids piling up
  /// duplicate pulls when the scheduler fires repeatedly). Returns true if a new
  /// row was created.
  Future<bool> enqueuePullOnce(String entity, {String payload = '{}'}) async {
    final pending = await _repo.queueByStatus('pending');
    final exists = pending.any(
      (r) =>
          r.entity == entity &&
          r.direction == SyncDirection.download.name &&
          r.operation == 'pull',
    );
    if (exists) return false;
    await enqueue(
      direction: SyncDirection.download,
      entity: entity,
      operation: 'pull',
      payload: payload,
    );
    return true;
  }

  /// Claims a batch of eligible rows and marks them in-flight.
  Future<List<SyncQueueData>> claim({int limit = 20}) =>
      _repo.claimBatch(limit: limit);

  Future<void> complete(SyncQueueData item) => _repo.markDone(item.id);

  /// Records a failure and schedules a retry (or dead-letters when exhausted).
  /// Returns whether the item will be retried.
  Future<bool> fail(SyncQueueData item, Object error) async {
    final attempts = item.attempts + 1;
    final willRetry = _retry.shouldRetry(attempts);
    final nextAt = willRetry ? _retry.nextAttemptTime(attempts) : null;
    await _repo.markAttemptFailed(
      id: item.id,
      attempts: attempts,
      error: error.toString(),
      nextAttemptAt: nextAt,
      willRetry: willRetry,
    );
    if (willRetry) {
      await _logger.warning(
        'Retry ${item.operation} ${item.entity} '
        '(attempt $attempts/${_retry.maxAttempts}) after $error',
        category: 'queue',
        entity: item.entity,
      );
    } else {
      await _logger.error(
        'Dead-lettered ${item.operation} ${item.entity} after $attempts attempts',
        category: 'queue',
        entity: item.entity,
        detail: error.toString(),
      );
    }
    return willRetry;
  }

  /// Resets rows abandoned as `inFlight` by a killed process back to `pending`.
  Future<int> recoverInterrupted() => _repo.recoverInFlight();

  Future<int> pendingCount() => _repo.countByStatus('pending');
  Future<int> deadLetterCount() => _repo.countByStatus('deadLetter');

  /// Removes completed rows to keep the table small.
  Future<int> clearCompleted() => _repo.purge('done');
}
