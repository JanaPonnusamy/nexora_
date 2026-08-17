import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/master_data/data/category_repository.dart';
import 'package:nexora_mobile/features/master_data/data/department_repository.dart';
import 'package:nexora_mobile/features/master_data/data/manufacturer_repository.dart';
import 'package:nexora_mobile/features/master_data/data/supplier_repository.dart';
import 'package:nexora_mobile/features/master_data/data/tax_rate_repository.dart';
import 'package:nexora_mobile/features/master_data/data/unit_repository.dart';
import 'package:nexora_mobile/features/master_data/domain/master_delta.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';

AppDatabase _memDb() => AppDatabase.withExecutor(NativeDatabase.memory());

const scope = MasterScope(tenantId: 't1', storeId: 's1', userId: 'u1');
const otherTenant = MasterScope(tenantId: 't2', storeId: 's1');

MasterDelta dept(
  List<Map<String, dynamic>> records, {
  List<String> deleted = const [],
}) =>
    MasterDelta(records: records, deletedIds: deleted);

void main() {
  group('DepartmentRepository (tenant-scoped)', () {
    late AppDatabase db;
    late DepartmentRepository repo;

    setUp(() {
      db = _memDb();
      repo = DepartmentRepository(db);
    });
    tearDown(() => db.close());

    test('first sync inserts records', () async {
      final changed = await repo.applyDelta(
        dept([
          {'id': 'd1', 'code': 'D1', 'name': 'Grocery'},
          {'id': 'd2', 'code': 'D2', 'name': 'Pharma'},
        ]),
        scope,
      );
      expect(changed, 2);
      expect(await repo.count(scope), 2);
      final all = await repo.getAll(scope);
      expect(all.map((d) => d.name), containsAll(['Grocery', 'Pharma']));
    });

    test('incremental sync updates an existing record', () async {
      await repo.applyDelta(
        dept([
          {'id': 'd1', 'name': 'Grocery'},
        ]),
        scope,
      );
      await repo.applyDelta(
        dept([
          {'id': 'd1', 'name': 'Grocery & Food'},
        ]),
        scope,
      );
      final d1 = await repo.getById(scope, 'd1');
      expect(d1!.name, 'Grocery & Food');
      expect(await repo.count(scope), 1);
    });

    test('deleted records are soft-deleted and hidden from reads', () async {
      await repo.applyDelta(
        dept([
          {'id': 'd1', 'name': 'A'},
          {'id': 'd2', 'name': 'B'},
        ]),
        scope,
      );
      final removed = await repo.applyDelta(dept([], deleted: ['d2']), scope);
      expect(removed, 1);
      expect(await repo.count(scope), 1);
      expect(await repo.getById(scope, 'd2'), isNull); // getAll/getById hide it
    });

    test('duplicate delta is idempotent (no duplicate rows)', () async {
      final records = [
        {'id': 'd1', 'name': 'A'},
      ];
      await repo.applyDelta(dept(records), scope);
      await repo.applyDelta(dept(records), scope);
      expect(await repo.count(scope), 1);
    });

    test('a locally-newer version is preserved (conflict handler)', () async {
      await repo.applyDelta(
        dept([
          {'id': 'd1', 'name': 'New', 'version': 5},
        ]),
        scope,
      );
      // Older server version must not overwrite.
      await repo.applyDelta(
        dept([
          {'id': 'd1', 'name': 'Stale', 'version': 3},
        ]),
        scope,
      );
      expect((await repo.getById(scope, 'd1'))!.name, 'New');
    });

    test('reads are tenant-scoped', () async {
      await repo.applyDelta(
        dept([
          {'id': 'd1', 'name': 'A'},
        ]),
        scope,
      );
      expect(await repo.count(otherTenant), 0);
      expect(await repo.getAll(otherTenant), isEmpty);
    });

    test('watchAll emits on change', () async {
      final future = repo.watchAll(scope).firstWhere((r) => r.isNotEmpty);
      await repo.applyDelta(
        dept([
          {'id': 'd1', 'name': 'A'},
        ]),
        scope,
      );
      expect((await future).single.name, 'A');
    });
  });

  group('SupplierRepository (store-scoped, full snapshot)', () {
    late AppDatabase db;
    late SupplierRepository repo;

    setUp(() {
      db = _memDb();
      repo = SupplierRepository(db);
    });
    tearDown(() => db.close());

    MasterDelta snapshot(List<Map<String, dynamic>> records) =>
        MasterDelta(records: records, fullSnapshot: true);

    test('first snapshot inserts suppliers', () async {
      await repo.applyDelta(
        snapshot([
          {'supplier_code': 'S1', 'supplier_name': 'Alpha', 'product_count': 3},
          {'supplier_code': 'S2', 'supplier_name': 'Beta'},
        ]),
        scope,
      );
      expect(await repo.count(scope), 2);
      expect((await repo.getByCode(scope, 'S1'))!.productCount, 3);
    });

    test('a later snapshot reconciles removals as soft-deletes', () async {
      await repo.applyDelta(
        snapshot([
          {'supplier_code': 'S1', 'supplier_name': 'Alpha'},
          {'supplier_code': 'S2', 'supplier_name': 'Beta'},
        ]),
        scope,
      );
      await repo.applyDelta(
        snapshot([
          {'supplier_code': 'S1', 'supplier_name': 'Alpha Renamed'},
        ]),
        scope,
      );
      expect(await repo.count(scope), 1);
      expect(
          (await repo.getByCode(scope, 'S1'))!.supplierName, 'Alpha Renamed');
      expect(await repo.getByCode(scope, 'S2'), isNull);
    });

    test('suppliers are store-scoped', () async {
      await repo.applyDelta(
        snapshot([
          {'supplier_code': 'S1', 'supplier_name': 'Alpha'},
        ]),
        scope,
      );
      const otherStore = MasterScope(tenantId: 't1', storeId: 's2');
      expect(await repo.count(otherStore), 0);
    });
  });

  group('other master repositories (smoke)', () {
    late AppDatabase db;
    setUp(() => db = _memDb());
    tearDown(() => db.close());

    test('category/manufacturer/unit/tax apply + count', () async {
      final cat = CategoryRepository(db);
      final man = ManufacturerRepository(db);
      final unit = UnitRepository(db);
      final tax = TaxRateRepository(db);

      await cat.applyDelta(
        dept([
          {'id': 'c1', 'name': 'Beverages', 'parent_id': 'root'},
        ]),
        scope,
      );
      await man.applyDelta(
        dept([
          {'id': 'm1', 'name': 'Acme'},
        ]),
        scope,
      );
      await unit.applyDelta(
        dept([
          {'id': 'u1', 'name': 'Each', 'code': 'EA'},
        ]),
        scope,
      );
      await tax.applyDelta(
        dept([
          {'id': 'tx1', 'name': 'GST 5%', 'rate_percent': 5.0},
        ]),
        scope,
      );

      expect(await cat.count(scope), 1);
      expect(await man.count(scope), 1);
      expect(await unit.count(scope), 1);
      expect(await tax.count(scope), 1);
      expect((await cat.getById(scope, 'c1'))!.parentId, 'root');
      expect((await tax.getById(scope, 'tx1'))!.ratePercent, 5.0);
    });
  });
}
