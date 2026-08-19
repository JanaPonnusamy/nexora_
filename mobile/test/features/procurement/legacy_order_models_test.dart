import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/procurement/domain/legacy_order_models.dart';

void main() {
  group('Legacy Order live shapes', () {
    test('store keeps a missing sync timestamp distinct from now', () {
      final store = LegacyStore.fromJson(const {
        'store_code': '7',
        'store_name': 'NMS',
        'server_name': '10.0.0.7',
        'database': 'NMS',
        'is_active': 1,
        'last_sync_time': null,
        'last_sync_status': 'FAILED',
      });

      expect(store.name, 'NMS');
      expect(store.lastSyncAt, isNull);
      expect(store.lastSyncFailed, isTrue);
    });

    test('database health carries state and access separately', () {
      final health = LegacyDbHealth.fromJson(const {
        'database': 'OrderNMC',
        'server': 'localhost',
        'reachable': true,
        'state': 'ONLINE',
        'access': 'SINGLE_USER',
        'online': false,
        'message': 'Database is ONLINE / SINGLE_USER.',
      });

      expect(health.reachable, isTrue);
      expect(health.online, isFalse);
      expect(health.state, 'ONLINE');
      expect(health.access, 'SINGLE_USER');
    });

    test('job progress is bounded and unknown states remain visible', () {
      final job = LegacyJob.fromJson(const {
        'job_id': 'abc',
        'kind': 'future-kind',
        'store_name': 'NMS',
        'status': 'paused',
        'step': 40,
        'total_steps': 20,
        'message': 'Waiting',
        'log': [],
      });

      expect(job.kind, LegacyJobKind.unknown);
      expect(job.status, LegacyJobStatus.unknown);
      expect(job.statusLabel, 'paused');
      expect(job.progress, 1);
    });

    test('running job parses logs and numeric strings', () {
      final job = LegacyJob.fromJson(const {
        'job_id': 'abc',
        'kind': 'order',
        'store_name': 'NMS',
        'status': 'running',
        'step': '3',
        'total_steps': '10',
        'message': 'Syncing PRODUCTS',
        'started_at': '2026-08-18T10:00:00',
        'log': [
          {'at': '2026-08-18T10:00:01', 'message': 'Starting sync'}
        ],
      });

      expect(job.kind, LegacyJobKind.order);
      expect(job.isRunning, isTrue);
      expect(job.progress, 0.3);
      expect(job.log.single.message, 'Starting sync');
    });

    test('qty row accepts SQL decimals and original date casing', () {
      final row = QtyCheckRow.fromJson(const {
        'productcode': 91,
        'productname': 'Paracetamol 500mg',
        'orderqty': '12',
        'totalstock': '4.000',
        'saleunit': 10,
        'unitdescription': '10 TABLETS',
        'slsqty': '28.5',
        'mrp': '25.50',
        'maxsaleqty': 8,
        'Transactiondate': '2026-08-18T09:30:00',
      });

      expect(row.productCode, 91);
      expect(row.orderQty, 12);
      expect(row.totalStock, 4);
      expect(row.salesQty, 28.5);
      expect(row.transactionAt, DateTime.parse('2026-08-18T09:30:00'));
    });

    test('missing legacy fields produce a renderable row', () {
      final row = QtyCheckRow.fromJson(const {});

      expect(row.productCode, 0);
      expect(row.productName, 'Unnamed product');
      expect(row.orderQty, 0);
    });
  });
}
