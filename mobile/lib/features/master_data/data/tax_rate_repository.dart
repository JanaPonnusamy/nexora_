import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/sync/conflict_handler.dart';
import 'package:nexora_mobile/features/master_data/data/master_repository.dart';
import 'package:nexora_mobile/features/master_data/data/master_write.dart';
import 'package:nexora_mobile/features/master_data/domain/master_delta.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';
import 'package:nexora_mobile/features/master_data/domain/tax_rate.dart';

/// Offline repository for tax-master entries (tenant-scoped, Drift-only).
class TaxRateRepository implements MasterWriter {
  TaxRateRepository(this._db, [ConflictHandler? conflict])
      : _conflict = conflict ??
            const ConflictHandler(strategy: ConflictStrategy.lastWriteWins);

  final AppDatabase _db;
  final ConflictHandler _conflict;

  Future<List<TaxRate>> getAll(
    MasterScope scope, {
    bool includeInactive = false,
  }) async {
    final query = _db.select(_db.taxMaster)
      ..where((t) => t.tenantId.equals(scope.tenantId) & t.isDeleted.equals(false))
      ..orderBy([(t) => OrderingTerm.asc(t.name)]);
    if (!includeInactive) {
      query.where((t) => t.isActive.equals(true));
    }
    final rows = await query.get();
    return rows.map(TaxRateMapper.fromRow).toList();
  }

  Stream<List<TaxRate>> watchAll(MasterScope scope) {
    return (_db.select(_db.taxMaster)
          ..where(
              (t) => t.tenantId.equals(scope.tenantId) & t.isDeleted.equals(false),)
          ..orderBy([(t) => OrderingTerm.asc(t.name)]))
        .watch()
        .map((rows) => rows.map(TaxRateMapper.fromRow).toList());
  }

  Future<TaxRate?> getById(MasterScope scope, String id) async {
    final row = await (_db.select(_db.taxMaster)
          ..where((t) =>
              t.tenantId.equals(scope.tenantId) &
              t.id.equals(id) &
              t.isDeleted.equals(false),))
        .getSingleOrNull();
    return row == null ? null : TaxRateMapper.fromRow(row);
  }

  @override
  Future<int> count(MasterScope scope) async {
    final counter = _db.taxMaster.id.count();
    final query = _db.selectOnly(_db.taxMaster)
      ..addColumns([counter])
      ..where(_db.taxMaster.tenantId.equals(scope.tenantId) &
          _db.taxMaster.isDeleted.equals(false),);
    return (await query.getSingle()).read(counter) ?? 0;
  }

  @override
  Future<int> applyDelta(MasterDelta delta, MasterScope scope) {
    return _db.transaction(() async {
      var changed = 0;
      final now = DateTime.now();
      final present = <String>{};

      for (final record in delta.records) {
        final dto = TaxRateDto.fromJson(record);
        if (dto.id.isEmpty) continue;
        present.add(dto.id);

        final existing = await (_db.select(_db.taxMaster)
              ..where(
                  (t) => t.tenantId.equals(scope.tenantId) & t.id.equals(dto.id),))
            .getSingleOrNull();

        final apply = shouldApplyRemote(
          _conflict,
          localExists: existing != null,
          localVersion: existing?.version,
          localUpdatedAt: existing?.serverUpdatedAt,
          remoteVersion: dto.version,
          remoteUpdatedAt: dto.updatedAt,
        );
        if (!apply) continue;

        await _db.into(_db.taxMaster).insertOnConflictUpdate(
              TaxRateMapper.toCompanion(dto, tenantId: scope.tenantId, syncedAt: now),
            );
        changed++;
      }

      if (delta.fullSnapshot) {
        changed += await _softDeleteMissing(scope, present, now);
      } else {
        for (final id in delta.deletedIds) {
          changed += await _markDeleted(scope, id, now);
        }
      }
      return changed;
    });
  }

  Future<int> _markDeleted(MasterScope scope, String id, DateTime now) =>
      (_db.update(_db.taxMaster)
            ..where((t) =>
                t.tenantId.equals(scope.tenantId) &
                t.id.equals(id) &
                t.isDeleted.equals(false),))
          .write(TaxMasterCompanion(
            isDeleted: const Value(true),
            syncedAt: Value(now),
          ),);

  Future<int> _softDeleteMissing(
    MasterScope scope,
    Set<String> present,
    DateTime now,
  ) async {
    final rows = await (_db.select(_db.taxMaster)
          ..where(
              (t) => t.tenantId.equals(scope.tenantId) & t.isDeleted.equals(false),))
        .get();
    var removed = 0;
    for (final row in rows) {
      if (!present.contains(row.id)) {
        removed += await _markDeleted(scope, row.id, now);
      }
    }
    return removed;
  }
}
