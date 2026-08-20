import 'dart:async';

import 'package:dio/dio.dart';
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/core/sync/delta_processor.dart';
import 'package:nexora_mobile/core/sync/sync_logger.dart';
import 'package:nexora_mobile/core/sync/sync_manager.dart';
import 'package:nexora_mobile/core/sync/sync_queue.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';
import 'package:nexora_mobile/core/sync/sync_status.dart';
import 'package:nexora_mobile/features/master_data/data/master_data_api_service.dart';
import 'package:nexora_mobile/features/master_data/data/supplier_repository.dart';
import 'package:nexora_mobile/features/master_data/domain/master_delta.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';
import 'package:nexora_mobile/features/master_data/sync/entity_delta_processors.dart';

/// Controllable connectivity for offline/online transitions.
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
  Future<void> dispose() async => _ctrl.close();
}

/// Fake supplier API — scripts the next full snapshot, no network.
class FakeSupplierApi extends MasterDataApiService {
  FakeSupplierApi() : super(Dio());
  MasterDelta? next;
  int calls = 0;

  @override
  Future<MasterDelta?> fetchSuppliers(
    MasterScope scope, {
    String? watermark,
  }) async {
    calls++;
    return next;
  }
}

MasterDelta snap(List<Map<String, dynamic>> records) =>
    MasterDelta(records: records, fullSnapshot: true);

void main() {
  const scope = MasterScope(tenantId: 't1', storeId: 's1', userId: 'u1');

  late AppDatabase db;
  late SyncRepository syncRepo;
  late SyncLogger logger;
  late SupplierRepository suppliers;
  late FakeSupplierApi api;
  late FakeConnectivity conn;

  SyncManager build() {
    final delta = DeltaProcessor(syncRepo, logger);
    final manager = SyncManager(
      queue: SyncQueue(syncRepo, logger),
      deltaProcessor: delta,
      connectivity: conn,
      repository: syncRepo,
      logger: logger,
    );
    manager.register(
      SupplierDeltaProcessor(
        repository: suppliers,
        api: api,
        scope: () => scope,
        logger: logger,
      ),
    );
    return manager;
  }

  setUp(() {
    db = AppDatabase.withExecutor(NativeDatabase.memory());
    syncRepo = SyncRepository(db);
    logger = SyncLogger(syncRepo);
    suppliers = SupplierRepository(db);
    api = FakeSupplierApi();
  });
  tearDown(() => db.close());

  test('first sync downloads suppliers into Drift', () async {
    conn = FakeConnectivity(NetworkStatus.online);
    api.next = snap([
      {'supplier_code': 'S1', 'supplier_name': 'Alpha'},
      {'supplier_code': 'S2', 'supplier_name': 'Beta'},
    ]);
    final manager = build();
    await manager.initialize();
    await manager.syncNow();

    expect(manager.state.status, SyncStatus.success);
    expect(await suppliers.count(scope), 2);
    final meta = await syncRepo.getMetadata(MasterEntities.suppliers);
    expect(meta!.lastStatus, 'success');
    expect(meta.recordCount, 2);
    await manager.dispose();
  });

  test('incremental sync applies updates and reconciles deletions', () async {
    conn = FakeConnectivity(NetworkStatus.online);
    final manager = build();
    await manager.initialize();

    api.next = snap([
      {'supplier_code': 'S1', 'supplier_name': 'Alpha'},
      {'supplier_code': 'S2', 'supplier_name': 'Beta'},
    ]);
    await manager.syncNow();
    expect(await suppliers.count(scope), 2);

    // S2 disappears, S1 renamed → full-snapshot reconcile removes S2.
    api.next = snap([
      {'supplier_code': 'S1', 'supplier_name': 'Alpha Renamed'},
    ]);
    await manager.syncNow();

    expect(await suppliers.count(scope), 1);
    expect(
      (await suppliers.getByCode(scope, 'S1'))!.supplierName,
      'Alpha Renamed',
    );
    expect(await suppliers.getByCode(scope, 'S2'), isNull);
    await manager.dispose();
  });

  test('offline defers sync but cached data stays readable', () async {
    // Seed cache while "online".
    conn = FakeConnectivity(NetworkStatus.online);
    api.next = snap([
      {'supplier_code': 'S1', 'supplier_name': 'Alpha'},
    ]);
    var manager = build();
    await manager.initialize();
    await manager.syncNow();
    await manager.dispose();

    // Restart offline.
    conn = FakeConnectivity(NetworkStatus.offline);
    manager = build();
    await manager.initialize();
    await manager.syncNow();

    expect(manager.state.status, SyncStatus.offline);
    // Repository still serves cached rows with no network.
    expect(await suppliers.count(scope), 1);
    await manager.dispose();
  });

  test('duplicate delta does not create duplicate rows', () async {
    conn = FakeConnectivity(NetworkStatus.online);
    final manager = build();
    await manager.initialize();
    final data = snap([
      {'supplier_code': 'S1', 'supplier_name': 'Alpha'},
    ]);
    api.next = data;
    await manager.syncNow();
    api.next = data; // identical again
    await manager.syncNow();
    expect(await suppliers.count(scope), 1);
    await manager.dispose();
  });

  test('restart recovers interrupted in-flight queue work', () async {
    conn = FakeConnectivity(NetworkStatus.online);
    // Simulate a killed run: a suppliers pull left in-flight.
    await syncRepo.enqueue(
      direction: SyncDirection.download.name,
      entity: MasterEntities.suppliers,
      operation: 'pull',
    );
    await syncRepo.claimBatch(); // → inFlight
    expect(await syncRepo.countByStatus('inFlight'), 1);

    api.next = snap([
      {'supplier_code': 'S1', 'supplier_name': 'Alpha'},
    ]);
    final manager = build();
    await manager.initialize(); // recovers inFlight → pending
    expect(await syncRepo.countByStatus('inFlight'), 0);

    await manager.syncNow();
    expect(await suppliers.count(scope), 1);
    await manager.dispose();
  });

  test('queue recovery drains a pending pull after reconnect', () async {
    conn = FakeConnectivity(NetworkStatus.offline);
    api.next = snap([
      {'supplier_code': 'S1', 'supplier_name': 'Alpha'},
    ]);
    final manager = build();
    await manager.initialize();
    await manager.syncNow(); // offline → nothing applied
    expect(await suppliers.count(scope), 0);

    conn.emit(NetworkStatus.online); // reconnect triggers auto-sync
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(await suppliers.count(scope), 1);
    await manager.dispose();
  });
}
