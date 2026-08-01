import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';

/// Persistence gateway for every sync-infrastructure table. This is the only
/// place that touches Drift for sync/agent data; higher layers (queue, manager,
/// agent) depend on this narrow, string-typed surface.
///
/// Deliberately imports `app_database` (which re-exports the generated data
/// classes) rather than `tables.dart`, so the domain `SyncState` model does not
/// collide with the `SyncState` Drift table.
class SyncRepository {
  SyncRepository(this._db);

  final AppDatabase _db;

  // --- Device information ----------------------------------------------------

  Future<DeviceInformationData?> readDevice() =>
      (_db.select(_db.deviceInformation)..where((t) => t.id.equals(1)))
          .getSingleOrNull();

  Future<void> upsertDevice(DeviceInformationCompanion device) =>
      _db.into(_db.deviceInformation).insertOnConflictUpdate(
            device.copyWith(id: const Value(1)),
          );

  Future<void> touchDeviceSeen(DateTime at) =>
      (_db.update(_db.deviceInformation)..where((t) => t.id.equals(1)))
          .write(DeviceInformationCompanion(lastSeenAt: Value(at)));

  // --- Configuration cache ---------------------------------------------------

  Future<void> putConfig(String key, String value, {int? version}) =>
      _db.into(_db.syncConfiguration).insertOnConflictUpdate(
            SyncConfigurationCompanion(
              key: Value(key),
              value: Value(value),
              version: version == null ? const Value.absent() : Value(version),
              updatedAt: Value(DateTime.now()),
            ),
          );

  Future<SyncConfigurationData?> getConfig(String key) =>
      (_db.select(_db.syncConfiguration)..where((t) => t.key.equals(key)))
          .getSingleOrNull();

  Stream<SyncConfigurationData?> watchConfig(String key) =>
      (_db.select(_db.syncConfiguration)..where((t) => t.key.equals(key)))
          .watchSingleOrNull();

  Future<List<SyncConfigurationData>> allConfig() =>
      _db.select(_db.syncConfiguration).get();

  // --- Per-entity metadata ---------------------------------------------------

  Future<SyncMetadataData?> getMetadata(String entity) =>
      (_db.select(_db.syncMetadata)..where((t) => t.entity.equals(entity)))
          .getSingleOrNull();

  Future<List<SyncMetadataData>> allMetadata() =>
      _db.select(_db.syncMetadata).get();

  Stream<List<SyncMetadataData>> watchMetadata() =>
      _db.select(_db.syncMetadata).watch();

  Future<void> upsertMetadata({
    required String entity,
    String? watermark,
    DateTime? lastSyncAt,
    String? lastStatus,
    int? recordCount,
  }) =>
      _db.into(_db.syncMetadata).insertOnConflictUpdate(
            SyncMetadataCompanion(
              entity: Value(entity),
              watermark:
                  watermark == null ? const Value.absent() : Value(watermark),
              lastSyncAt:
                  lastSyncAt == null ? const Value.absent() : Value(lastSyncAt),
              lastStatus:
                  lastStatus == null ? const Value.absent() : Value(lastStatus),
              recordCount: recordCount == null
                  ? const Value.absent()
                  : Value(recordCount),
              updatedAt: Value(DateTime.now()),
            ),
          );

  // --- Persisted engine state ------------------------------------------------

  Future<SyncStateData?> readState() =>
      (_db.select(_db.syncState)..where((t) => t.id.equals(1)))
          .getSingleOrNull();

  Future<void> writeState({
    required String status,
    DateTime? lastRunAt,
    DateTime? lastSuccessAt,
    String? lastError,
    bool clearError = false,
    int? pendingCount,
  }) =>
      _db.into(_db.syncState).insertOnConflictUpdate(
            SyncStateCompanion(
              id: const Value(1),
              status: Value(status),
              lastRunAt:
                  lastRunAt == null ? const Value.absent() : Value(lastRunAt),
              lastSuccessAt: lastSuccessAt == null
                  ? const Value.absent()
                  : Value(lastSuccessAt),
              lastError: clearError ? const Value(null) : Value(lastError),
              pendingCount: pendingCount == null
                  ? const Value.absent()
                  : Value(pendingCount),
              updatedAt: Value(DateTime.now()),
            ),
          );

  // --- Operation queue -------------------------------------------------------

  Future<int> enqueue({
    required String direction,
    required String entity,
    required String operation,
    String payload = '{}',
    int maxAttempts = 5,
  }) =>
      _db.into(_db.syncQueue).insert(
            SyncQueueCompanion.insert(
              direction: direction,
              entity: entity,
              operation: operation,
              payload: Value(payload),
              maxAttempts: Value(maxAttempts),
            ),
          );

  Future<List<SyncQueueData>> queueByStatus(String status) =>
      (_db.select(_db.syncQueue)..where((t) => t.status.equals(status))).get();

  Stream<List<SyncQueueData>> watchQueue() => (_db.select(_db.syncQueue)
        ..orderBy([(t) => OrderingTerm.desc(t.updatedAt)]))
      .watch();

  Future<int> countByStatus(String status) async {
    final count = _db.syncQueue.id.count();
    final query = _db.selectOnly(_db.syncQueue)
      ..addColumns([count])
      ..where(_db.syncQueue.status.equals(status));
    final row = await query.getSingle();
    return row.read(count) ?? 0;
  }

  /// Atomically claims up to [limit] eligible rows (pending and past their
  /// backoff), marking them `inFlight`, and returns them. Concurrency-safe via
  /// a transaction so two drains never grab the same row.
  Future<List<SyncQueueData>> claimBatch({
    int limit = 20,
    DateTime? now,
  }) {
    final ts = now ?? DateTime.now();
    return _db.transaction(() async {
      final eligible = await (_db.select(_db.syncQueue)
            ..where((t) =>
                t.status.equals('pending') &
                (t.nextAttemptAt.isNull() |
                    t.nextAttemptAt.isSmallerOrEqualValue(ts)),)
            ..orderBy([(t) => OrderingTerm.asc(t.createdAt)])
            ..limit(limit))
          .get();

      for (final row in eligible) {
        await (_db.update(_db.syncQueue)..where((t) => t.id.equals(row.id)))
            .write(SyncQueueCompanion(
          status: const Value('inFlight'),
          updatedAt: Value(ts),
        ),);
      }
      return eligible;
    });
  }

  Future<void> markDone(int id) =>
      (_db.update(_db.syncQueue)..where((t) => t.id.equals(id))).write(
        SyncQueueCompanion(
          status: const Value('done'),
          updatedAt: Value(DateTime.now()),
          lastError: const Value(null),
        ),
      );

  /// Records a failed attempt. Either schedules a retry (`pending` with a
  /// backoff [nextAttemptAt]) or moves the row to `deadLetter` once exhausted.
  Future<void> markAttemptFailed({
    required int id,
    required int attempts,
    required String error,
    DateTime? nextAttemptAt,
    required bool willRetry,
  }) =>
      (_db.update(_db.syncQueue)..where((t) => t.id.equals(id))).write(
        SyncQueueCompanion(
          status: Value(willRetry ? 'pending' : 'deadLetter'),
          attempts: Value(attempts),
          nextAttemptAt: Value(nextAttemptAt),
          lastError: Value(error),
          updatedAt: Value(DateTime.now()),
        ),
      );

  /// On startup, any row left `inFlight` by a killed process is reset to
  /// `pending` so it resumes. Returns the number of rows recovered.
  Future<int> recoverInFlight() =>
      (_db.update(_db.syncQueue)..where((t) => t.status.equals('inFlight')))
          .write(SyncQueueCompanion(
        status: const Value('pending'),
        updatedAt: Value(DateTime.now()),
      ),);

  Future<int> purge(String status) =>
      (_db.delete(_db.syncQueue)..where((t) => t.status.equals(status))).go();

  // --- History / logging -----------------------------------------------------

  Future<void> appendHistory({
    required String level,
    required String category,
    required String message,
    String? entity,
    String? detail,
  }) =>
      _db.into(_db.syncHistory).insert(
            SyncHistoryCompanion.insert(
              level: Value(level),
              category: Value(category),
              message: message,
              entity: Value(entity),
              detail: Value(detail),
            ),
          );

  Future<List<SyncHistoryData>> recentHistory({int limit = 100}) =>
      (_db.select(_db.syncHistory)
            ..orderBy([(t) => OrderingTerm.desc(t.createdAt)])
            ..limit(limit))
          .get();

  Stream<List<SyncHistoryData>> watchHistory({int limit = 100}) =>
      (_db.select(_db.syncHistory)
            ..orderBy([(t) => OrderingTerm.desc(t.createdAt)])
            ..limit(limit))
          .watch();

  /// Keeps the history bounded: deletes all but the newest [keep] rows.
  Future<void> trimHistory({int keep = 500}) async {
    final cutoff = await (_db.select(_db.syncHistory)
          ..orderBy([(t) => OrderingTerm.desc(t.createdAt)])
          ..limit(1, offset: keep))
        .getSingleOrNull();
    if (cutoff == null) return;
    await (_db.delete(_db.syncHistory)
          ..where((t) => t.createdAt.isSmallerOrEqualValue(cutoff.createdAt)))
        .go();
  }
}
