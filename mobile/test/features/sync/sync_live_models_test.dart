import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/sync/data/sync_live_models.dart';

/// `GET /api/sync/live` is assembled from raw SQL with `ISNULL` defaults and
/// left joins, so nulls and missing keys are normal traffic. These lock down
/// that a sparse row still yields a usable card rather than throwing.
void main() {
  group('LiveSyncExecution', () {
    test('parses a full row', () {
      final e = LiveSyncExecution.fromJson(const {
        'store_id': 's-1',
        'store_code': 'NMA',
        'store_name': 'Nathan Medicals A',
        'execution_id': 'exec-9',
        'status': 'RUNNING',
        'sync_type': 'DELTA',
        'current_table': 'dbo.Products',
        'chunk_no': 4,
        'total_chunks': 10,
        'rows_processed': 400,
        'total_rows': 1000,
        'rows_remaining': 600,
        'execution_rows_processed': 2500,
        'execution_total_rows': 10000,
        'rows_changed': 120,
        'rows_uploaded': 118,
        'speed_rows_sec': 42.5,
        'eta_seconds': 90,
        'progress_pct': 40.0,
        'started_at': '2026-08-16T09:00:00',
      });

      expect(e.label, 'Nathan Medicals A');
      expect(e.isPaused, isFalse);
      expect(e.tableProgress, 0.4);
      expect(e.executionProgress, 0.25);
      expect(e.eta, const Duration(seconds: 90));
      expect(e.speedRowsSec, 42.5);
    });

    test('a row with no totals reports indeterminate progress, not zero', () {
      // The agent has not sent per-table totals yet. Claiming 0% would assert
      // progress information the server has not actually produced.
      final e = LiveSyncExecution.fromJson(const {
        'store_id': 's-2',
        'execution_id': 'exec-1',
        'status': 'RUNNING',
        'total_rows': null,
        'execution_total_rows': null,
      });

      expect(e.tableProgress, isNull);
      expect(e.executionProgress, isNull);
      expect(e.rowsProcessed, 0);
    });

    test('a zero total is treated as unknown, not as a division by zero', () {
      final e = LiveSyncExecution.fromJson(const {
        'store_id': 's-3',
        'execution_id': 'x',
        'status': 'RUNNING',
        'execution_total_rows': 0,
        'execution_rows_processed': 0,
      });

      expect(e.executionProgress, isNull);
    });

    test('progress is clamped when the agent over-reports', () {
      final e = LiveSyncExecution.fromJson(const {
        'store_id': 's-4',
        'execution_id': 'x',
        'status': 'RUNNING',
        'execution_rows_processed': 1200,
        'execution_total_rows': 1000,
      });

      expect(e.executionProgress, 1.0);
    });

    test('falls back through name, code, then id for a label', () {
      expect(
        LiveSyncExecution.fromJson(const {
          'store_id': 's-5',
          'store_code': 'NMB',
          'execution_id': 'x',
          'status': 'RUNNING',
        }).label,
        'NMB',
      );
      expect(
        LiveSyncExecution.fromJson(const {
          'store_id': 's-5',
          'execution_id': 'x',
          'status': 'RUNNING',
        }).label,
        's-5',
      );
    });

    test('numbers arriving as strings still parse', () {
      // The SQL layer has returned Decimal-as-string for these before.
      final e = LiveSyncExecution.fromJson(const {
        'store_id': 's-6',
        'execution_id': 'x',
        'status': 'PAUSED',
        'execution_rows_processed': '250',
        'execution_total_rows': '1000',
        'speed_rows_sec': '12.5',
      });

      expect(e.isPaused, isTrue);
      expect(e.executionProgress, 0.25);
      expect(e.speedRowsSec, 12.5);
    });

    test('an unparseable date leaves elapsed unknown rather than throwing', () {
      final e = LiveSyncExecution.fromJson(const {
        'store_id': 's-7',
        'execution_id': 'x',
        'status': 'RUNNING',
        'started_at': 'not-a-date',
      });

      expect(e.startedAt, isNull);
      expect(e.elapsed, isNull);
    });
  });

  group('SyncHistoryEntry', () {
    test('reads the status under either key the endpoint has used', () {
      expect(
        SyncHistoryEntry.fromJson(const {
          'execution_id': 'a',
          'execution_status': 'COMPLETED',
        }).isSuccess,
        isTrue,
      );
      expect(
        SyncHistoryEntry.fromJson(const {
          'execution_id': 'b',
          'status': 'FAILED',
        }).isFailure,
        isTrue,
      );
    });

    test('a cancelled run counts as a failure for colouring', () {
      final e = SyncHistoryEntry.fromJson(const {
        'execution_id': 'c',
        'execution_status': 'CANCELLED',
      });

      expect(e.isFailure, isTrue);
      expect(e.isSuccess, isFalse);
    });

    test('duration needs both ends', () {
      final complete = SyncHistoryEntry.fromJson(const {
        'execution_id': 'd',
        'execution_status': 'COMPLETED',
        'started_at': '2026-08-16T09:00:00',
        'completed_at': '2026-08-16T09:04:30',
      });
      expect(complete.duration, const Duration(minutes: 4, seconds: 30));

      final running = SyncHistoryEntry.fromJson(const {
        'execution_id': 'e',
        'execution_status': 'RUNNING',
        'started_at': '2026-08-16T09:00:00',
      });
      expect(running.duration, isNull);
    });

    test('row totals are read under either historical key', () {
      expect(
        SyncHistoryEntry.fromJson(const {
          'execution_id': 'f',
          'rows_synced': 120,
        }).rowsSynced,
        120,
      );
      expect(
        SyncHistoryEntry.fromJson(const {
          'execution_id': 'g',
          'total_rows': 340,
        }).rowsSynced,
        340,
      );
    });
  });

  group('SyncControlAction', () {
    test('sends the exact strings control_stores branches on', () {
      // The server maps PAUSE→PAUSED and STOP→CANCELLED; anything else is
      // silently treated as STOP, so these strings must not drift.
      expect(SyncControlAction.pause.wire, 'PAUSE');
      expect(SyncControlAction.stop.wire, 'STOP');
    });
  });

  group('SyncControlResult', () {
    test('reports how many executions actually changed', () {
      final r = SyncControlResult.fromJson(const {
        'affected': 2,
        'action': 'PAUSE',
        'status': 'PAUSED',
      });
      expect(r.affected, 2);
      expect(r.action, 'PAUSE');
    });

    test('an empty response reads as nothing affected', () {
      expect(SyncControlResult.fromJson(const {}).affected, 0);
    });
  });
}
