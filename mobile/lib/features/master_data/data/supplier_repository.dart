import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/sync/conflict_handler.dart';
import 'package:nexora_mobile/features/master_data/data/master_repository.dart';
import 'package:nexora_mobile/features/master_data/data/master_write.dart';
import 'package:nexora_mobile/features/master_data/domain/master_delta.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';
import 'package:nexora_mobile/features/master_data/domain/supplier.dart';

/// Offline repository for suppliers. Store-scoped (tenant + store) and
/// Drift-only. The supplier endpoint returns a full snapshot, so [applyDelta]
/// reconciles local rows not present in the snapshot as soft-deleted.
class SupplierRepository implements MasterWriter {
  SupplierRepository(this._db, [ConflictHandler? conflict])
      : _conflict = conflict ??
            const ConflictHandler(strategy: ConflictStrategy.lastWriteWins);

  final AppDatabase _db;
  final ConflictHandler _conflict;

  Future<List<Supplier>> getAll(
    MasterScope scope, {
    bool includeInactive = false,
  }) async {
    final query = _db.select(_db.suppliers)
      ..where(
        (t) =>
            t.tenantId.equals(scope.tenantId) &
            t.storeId.equals(scope.storeId ?? '') &
            t.isDeleted.equals(false),
      )
      ..orderBy([(t) => OrderingTerm.asc(t.supplierName)]);
    if (!includeInactive) {
      query.where((t) => t.isActive.equals(true));
    }
    final rows = await query.get();
    return rows.map(SupplierMapper.fromRow).toList();
  }

  Stream<List<Supplier>> watchAll(MasterScope scope) {
    return (_db.select(_db.suppliers)
          ..where(
            (t) =>
                t.tenantId.equals(scope.tenantId) &
                t.storeId.equals(scope.storeId ?? '') &
                t.isDeleted.equals(false),
          )
          ..orderBy([(t) => OrderingTerm.asc(t.supplierName)]))
        .watch()
        .map((rows) => rows.map(SupplierMapper.fromRow).toList());
  }

  Future<Supplier?> getByCode(MasterScope scope, String supplierCode) async {
    final row = await (_db.select(_db.suppliers)
          ..where(
            (t) =>
                t.tenantId.equals(scope.tenantId) &
                t.storeId.equals(scope.storeId ?? '') &
                t.supplierCode.equals(supplierCode) &
                t.isDeleted.equals(false),
          ))
        .getSingleOrNull();
    return row == null ? null : SupplierMapper.fromRow(row);
  }

  @override
  Future<int> count(MasterScope scope) async {
    final counter = _db.suppliers.supplierCode.count();
    final query = _db.selectOnly(_db.suppliers)
      ..addColumns([counter])
      ..where(
        _db.suppliers.tenantId.equals(scope.tenantId) &
            _db.suppliers.storeId.equals(scope.storeId ?? '') &
            _db.suppliers.isDeleted.equals(false),
      );
    return (await query.getSingle()).read(counter) ?? 0;
  }

  @override
  Future<int> applyDelta(MasterDelta delta, MasterScope scope) {
    final storeId = scope.storeId ?? '';
    return _db.transaction(() async {
      var changed = 0;
      final now = DateTime.now();
      final present = <String>{};

      for (final record in delta.records) {
        final dto = SupplierDto.fromJson(record);
        if (dto.supplierCode.isEmpty) continue;
        present.add(dto.supplierCode);

        final existing = await (_db.select(_db.suppliers)
              ..where(
                (t) =>
                    t.tenantId.equals(scope.tenantId) &
                    t.storeId.equals(storeId) &
                    t.supplierCode.equals(dto.supplierCode),
              ))
            .getSingleOrNull();

        // Supplier records carry no server version; conflict handling falls back
        // to server-authoritative (see shouldApplyRemote).
        final apply = shouldApplyRemote(
          _conflict,
          localExists: existing != null,
          localVersion: existing?.version,
          remoteVersion: null,
        );
        if (!apply) continue;

        await _db.into(_db.suppliers).insertOnConflictUpdate(
              SupplierMapper.toCompanion(
                dto,
                tenantId: scope.tenantId,
                storeId: storeId,
                syncedAt: now,
              ),
            );
        changed++;
      }

      if (delta.fullSnapshot) {
        changed += await _softDeleteMissing(scope, storeId, present, now);
      } else {
        for (final code in delta.deletedIds) {
          changed += await _markDeleted(scope, storeId, code, now);
        }
      }
      return changed;
    });
  }

  Future<int> _markDeleted(
    MasterScope scope,
    String storeId,
    String code,
    DateTime now,
  ) =>
      (_db.update(_db.suppliers)
            ..where(
              (t) =>
                  t.tenantId.equals(scope.tenantId) &
                  t.storeId.equals(storeId) &
                  t.supplierCode.equals(code) &
                  t.isDeleted.equals(false),
            ))
          .write(
        SuppliersCompanion(
          isDeleted: const Value(true),
          syncedAt: Value(now),
        ),
      );

  Future<int> _softDeleteMissing(
    MasterScope scope,
    String storeId,
    Set<String> present,
    DateTime now,
  ) async {
    final rows = await (_db.select(_db.suppliers)
          ..where(
            (t) =>
                t.tenantId.equals(scope.tenantId) &
                t.storeId.equals(storeId) &
                t.isDeleted.equals(false),
          ))
        .get();
    var removed = 0;
    for (final row in rows) {
      if (!present.contains(row.supplierCode)) {
        removed += await _markDeleted(scope, storeId, row.supplierCode, now);
      }
    }
    return removed;
  }
}
