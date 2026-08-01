import 'dart:async';

import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/core/sync/delta_processor.dart';
import 'package:nexora_mobile/core/sync/retry_policy.dart';
import 'package:nexora_mobile/core/sync/sync_logger.dart';
import 'package:nexora_mobile/core/sync/sync_manager.dart';
import 'package:nexora_mobile/core/sync/sync_queue.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';
import 'package:nexora_mobile/core/sync/sync_status.dart';

/// Controllable connectivity double for driving offline/online transitions.
class FakeConnectivity extends ConnectivityService {
  FakeConnectivity(this._status);

  NetworkStatus _status;
  final _ctrl = StreamController<NetworkStatus>.broadcast();

  @override
  NetworkStatus get lastKnown => _status;

  @override
  Stream<NetworkStatus> get statusStream => _ctrl.stream;

  @override
  Future<void> start() async {}

  @override
  Future<NetworkStatus> check() async => _status;

  void emit(NetworkStatus s) {
    _status = s;
    _ctrl.add(s);
  }

  @override
  Future<void> dispose() async {
    await _ctrl.close();
  }
}

/// Delta processor whose behaviour is scripted per-test.
class TestProcessor extends EntityDeltaProcessor {
  TestProcessor(this.entity, {this.failTimes = 0});

  @override
  final String entity;

  int failTimes;
  int pulls = 0;

  @override
  Future<DeltaResult> pull({
    String? watermark,
    Map<String, dynamic> params = const {},
  }) async {
    pulls++;
    if (failTimes > 0) {
      failTimes--;
      throw StateError('scripted failure');
    }
    return DeltaResult(
      entity: entity,
      changed: 1,
      recordCount: 1,
      nextWatermark: 'wm-$pulls',
    );
  }
}

AppDatabase _memDb() => AppDatabase.withExecutor(NativeDatabase.memory());

void main() {
  group('SyncRepository', () {
    late AppDatabase db;
    late SyncRepository repo;

    setUp(() {
      db = _memDb();
      repo = SyncRepository(db);
    });
    tearDown(() => db.close());

    test('config put/get and version stays via caller', () async {
      await repo.putConfig('k', 'v1', version: 1);
      final row = await repo.getConfig('k');
      expect(row!.value, 'v1');
      expect(row.version, 1);
    });

    test('metadata upsert accumulates', () async {
      await repo.upsertMetadata(
        entity: 'e',
        watermark: 'w',
        recordCount: 5,
        lastStatus: 'success',
      );
      final m = await repo.getMetadata('e');
      expect(m!.watermark, 'w');
      expect(m.recordCount, 5);
      expect(m.lastStatus, 'success');
    });

    test('queue claim marks inFlight and recover resets it', () async {
      await repo.enqueue(direction: 'download', entity: 'e', operation: 'pull');
      final claimed = await repo.claimBatch();
      expect(claimed, hasLength(1));
      expect(await repo.countByStatus('inFlight'), 1);
      expect(await repo.countByStatus('pending'), 0);

      final recovered = await repo.recoverInFlight();
      expect(recovered, 1);
      expect(await repo.countByStatus('pending'), 1);
    });

    test('history append + trim keeps only newest', () async {
      for (var i = 0; i < 10; i++) {
        await repo.appendHistory(
          level: 'info',
          category: 'test',
          message: 'm$i',
        );
      }
      await repo.trimHistory(keep: 3);
      final rows = await repo.recentHistory();
      expect(rows.length, lessThanOrEqualTo(3));
    });

    test('state write/read round-trips', () async {
      final now = DateTime(2026, 5, 1);
      await repo.writeState(
        status: 'success',
        lastRunAt: now,
        lastSuccessAt: now,
        pendingCount: 0,
      );
      final s = await repo.readState();
      expect(s!.status, 'success');
      expect(s.lastRunAt, now);
    });
  });

  group('SyncQueue', () {
    late AppDatabase db;
    late SyncQueue queue;

    setUp(() {
      db = _memDb();
      final repo = SyncRepository(db);
      queue = SyncQueue(repo, SyncLogger(repo), retryPolicy: RetryPolicy.test);
    });
    tearDown(() => db.close());

    test('enqueuePullOnce de-duplicates pending pulls', () async {
      expect(await queue.enqueuePullOnce('e'), isTrue);
      expect(await queue.enqueuePullOnce('e'), isFalse);
      expect(await queue.pendingCount(), 1);
    });

    test('fail retries then dead-letters when exhausted', () async {
      // Zero backoff so the retry is immediately eligible for re-claim
      // (Drift persists DateTime at second precision).
      final repo = SyncRepository(db);
      final q = SyncQueue(
        repo,
        SyncLogger(repo),
        retryPolicy:
            const RetryPolicy(maxAttempts: 2, baseDelay: Duration.zero, jitter: false),
      );
      await q.enqueue(
        direction: SyncDirection.download,
        entity: 'e',
        operation: 'pull',
      );

      var item = (await q.claim()).single;
      expect(await q.fail(item, 'boom'), isTrue); // attempt 1 → retry

      item = (await q.claim()).single; // eligible again
      expect(item.attempts, 1);
      expect(await q.fail(item, 'boom'), isFalse); // attempt 2 → dead-letter

      expect(await repo.countByStatus('deadLetter'), 1);
      expect(await q.pendingCount(), 0);
    });

    test('complete moves an item to done', () async {
      await queue.enqueue(
        direction: SyncDirection.download,
        entity: 'e',
        operation: 'pull',
      );
      final item = (await queue.claim()).single;
      await queue.complete(item);
      expect(await queue.pendingCount(), 0);
      final done = await queue.clearCompleted();
      expect(done, 1);
    });
  });

  group('SyncManager', () {
    late AppDatabase db;
    late SyncRepository repo;
    late SyncLogger logger;

    setUp(() {
      db = _memDb();
      repo = SyncRepository(db);
      logger = SyncLogger(repo);
    });
    tearDown(() => db.close());

    SyncManager build(
      FakeConnectivity conn, {
      RetryPolicy retry = const RetryPolicy(),
      List<EntityDeltaProcessor> processors = const [],
    }) {
      final delta = DeltaProcessor(repo, logger);
      final manager = SyncManager(
        queue: SyncQueue(repo, logger, retryPolicy: retry),
        deltaProcessor: delta,
        connectivity: conn,
        repository: repo,
        logger: logger,
      );
      for (final p in processors) {
        manager.register(p);
      }
      return manager;
    }

    test('offline defers work and reports offline', () async {
      final conn = FakeConnectivity(NetworkStatus.offline);
      final manager = build(conn, processors: [TestProcessor('e')]);
      await manager.initialize();
      await manager.syncNow();
      expect(manager.state.status, SyncStatus.offline);
      await manager.dispose();
    });

    test('online cycle processes queued pulls and succeeds', () async {
      final conn = FakeConnectivity(NetworkStatus.online);
      final proc = TestProcessor('e');
      final manager = build(conn, processors: [proc]);
      await manager.initialize();
      await manager.syncNow();

      expect(manager.state.status, SyncStatus.success);
      expect(manager.state.failed, 0);
      expect(proc.pulls, greaterThanOrEqualTo(1));

      final meta = await repo.getMetadata('e');
      expect(meta!.lastStatus, 'success');
      expect(meta.watermark, isNotNull);
      await manager.dispose();
    });

    test('failed processor dead-letters and reports failure', () async {
      final conn = FakeConnectivity(NetworkStatus.online);
      final proc = TestProcessor('e', failTimes: 5);
      final manager = build(
        conn,
        retry: const RetryPolicy(maxAttempts: 1),
        processors: [proc],
      );
      await manager.initialize();
      await manager.syncNow();

      expect(manager.state.failed, 1);
      expect(manager.state.status, SyncStatus.failed);
      await manager.dispose();
    });

    test('reconnect triggers an automatic sync', () async {
      final conn = FakeConnectivity(NetworkStatus.offline);
      final proc = TestProcessor('e');
      final manager = build(conn, processors: [proc]);
      await manager.initialize();
      await manager.syncNow();
      expect(manager.state.status, SyncStatus.offline);

      conn.emit(NetworkStatus.online);
      // Allow the reconnect-triggered cycle to run.
      await Future<void>.delayed(const Duration(milliseconds: 50));
      expect(proc.pulls, greaterThanOrEqualTo(1));
      await manager.dispose();
    });

    test('initialize recovers interrupted in-flight work', () async {
      // Leave a row stuck in-flight (as a killed process would).
      await repo.enqueue(direction: 'download', entity: 'e', operation: 'pull');
      await repo.claimBatch(); // → inFlight
      expect(await repo.countByStatus('inFlight'), 1);

      final conn = FakeConnectivity(NetworkStatus.offline);
      final manager = build(conn, processors: [TestProcessor('e')]);
      await manager.initialize();

      expect(await repo.countByStatus('inFlight'), 0);
      expect(await repo.countByStatus('pending'), 1);
      await manager.dispose();
    });
  });
}
