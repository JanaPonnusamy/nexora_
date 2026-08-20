import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/features/sync/data/sync_control_center.dart';

void main() {
  group('SyncKpis', () {
    test('parses all fields and derives totalStores', () {
      final kpis = SyncKpis.fromJson(const {
        'stores_online': 6,
        'stores_offline': 1,
        'sync_running': 0,
        'queued': 2,
        'completed_today': 14,
        'failed_today': 1,
      });
      expect(kpis.storesOnline, 6);
      expect(kpis.storesOffline, 1);
      expect(kpis.totalStores, 7);
      expect(kpis.syncRunning, 0);
      expect(kpis.queued, 2);
      expect(kpis.completedToday, 14);
      expect(kpis.failedToday, 1);
    });

    test('missing fields default to zero', () {
      final kpis = SyncKpis.fromJson(const {});
      expect(kpis.storesOnline, 0);
      expect(kpis.totalStores, 0);
    });
  });

  group('StoreSyncStatus', () {
    test('parses an online, idle store', () {
      final s = StoreSyncStatus.fromJson({
        'store_id': 'abc-123',
        'store_code': 'NMA',
        'store_name': 'Nathan Medicals A',
        'connection_type': 'LAN',
        'agent_status': 'Online',
        'last_sync': '2026-08-02T18:37:00',
        'current_activity': 'Idle',
        'is_syncing': false,
        'status': 'Online',
      });
      expect(s.storeCode, 'NMA');
      expect(s.isOnline, isTrue);
      expect(s.isSyncing, isFalse);
      expect(s.status, 'Online');
      expect(s.lastSync, DateTime.parse('2026-08-02T18:37:00'));
    });

    test('a syncing store reports isSyncing true regardless of status label',
        () {
      final s = StoreSyncStatus.fromJson({
        'store_id': 's2',
        'store_code': 'NMC',
        'store_name': 'Nathan Medicals C',
        'connection_type': 'LAN',
        'agent_status': 'Online',
        'current_activity': 'Syncing',
        'is_syncing': true,
        'status': 'Syncing',
      });
      expect(s.isSyncing, isTrue);
      expect(s.status, 'Syncing');
    });

    test('an offline store has no last_sync and defaults gracefully', () {
      final s = StoreSyncStatus.fromJson(const {
        'store_id': 's3',
        'store_code': 'NMG',
        'store_name': 'Nathan Medicals G',
      });
      expect(s.isOnline, isFalse);
      expect(s.agentStatus, 'Offline');
      expect(s.currentActivity, 'Idle');
      expect(s.lastSync, isNull);
    });
  });

  group('SyncControlCenter', () {
    test('parses the full control-center payload', () {
      final cc = SyncControlCenter.fromJson({
        'kpis': {
          'stores_online': 6,
          'stores_offline': 0,
          'sync_running': 0,
          'queued': 0,
          'completed_today': 6,
          'failed_today': 0,
        },
        'stores': [
          {
            'store_id': 's1',
            'store_code': 'NMA',
            'store_name': 'Nathan Medicals A',
            'agent_status': 'Online',
            'current_activity': 'Idle',
            'is_syncing': false,
            'status': 'Online',
          },
        ],
      });
      expect(cc.kpis.storesOnline, 6);
      expect(cc.stores, hasLength(1));
      expect(cc.stores.single.storeCode, 'NMA');
    });

    test('a missing or malformed stores list yields an empty list, not a crash',
        () {
      final cc = SyncControlCenter.fromJson(const {'kpis': {}});
      expect(cc.stores, isEmpty);

      final cc2 = SyncControlCenter.fromJson(const {
        'kpis': {},
        'stores': 'not-a-list',
      });
      expect(cc2.stores, isEmpty);
    });
  });
}
