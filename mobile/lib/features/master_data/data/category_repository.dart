import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/sync/conflict_handler.dart';
import 'package:nexora_mobile/features/master_data/data/master_repository.dart';
import 'package:nexora_mobile/features/master_data/data/master_write.dart';
import 'package:nexora_mobile/features/master_data/domain/category.dart';
import 'package:nexora_mobile/features/master_data/domain/master_delta.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';

/// Offline repository for product categories (tenant-scoped, Drift-only).
class CategoryRepository implements MasterWriter {
  CategoryRepository(this._db, [ConflictHandler? conflict])
      : _conflict = conflict ??
            const ConflictHandler(strategy: ConflictStrategy.lastWriteWins);

  final AppDatabase _db;
  final ConflictHandler _conflict;

  Future<List<Category>> getAll(
    MasterScope scope, {
    bool includeInactive = false,
  }) async {
    final query = _db.select(_db.categories)
      ..where((t) => t.tenantId.equals(scope.tenantId) & t.isDeleted.equals(false))
      ..orderBy([(t) => OrderingTerm.asc(t.name)]);
    if (!includeInactive) {
      query.where((t) => t.isActive.equals(true));
    }
    final rows = await query.get();
    return rows.map(CategoryMapper.fromRow).toList();
  }

  Stream<List<Category>> watchAll(MasterScope scope) {
    return (_db.select(_db.categories)
          ..where(
              (t) => t.tenantId.equals(scope.tenantId) & t.isDeleted.equals(false),)
          ..orderBy([(t) => OrderingTerm.asc(t.name)]))
        .watch()
        .map((rows) => rows.map(CategoryMapper.fromRow).toList());
  }

  Future<Category?> getById(MasterScope scope, String id) async {
    final row = await (_db.select(_db.categories)
          ..where((t) =>
              t.tenantId.equals(scope.tenantId) &
              t.id.equals(id) &
              t.isDeleted.equals(false),))
        .getSingleOrNull();
    return row == null ? null : CategoryMapper.fromRow(row);
  }

  @override
  Future<int> count(MasterScope scope) async {
    final counter = _db.categories.id.count();
    final query = _db.selectOnly(_db.categories)
      ..addColumns([counter])
      ..where(_db.categories.tenantId.equals(scope.tenantId) &
          _db.categories.isDeleted.equals(false),);
    return (await query.getSingle()).read(counter) ?? 0;
  }

  @override
  Future<int> applyDelta(MasterDelta delta, MasterScope scope) {
    return _db.transaction(() async {
      var changed = 0;
      final now = DateTime.now();
      final present = <String>{};

      for (final record in delta.records) {
        final dto = CategoryDto.fromJson(record);
        if (dto.id.isEmpty) continue;
        present.add(dto.id);

        final existing = await (_db.select(_db.categories)
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

        await _db.into(_db.categories).insertOnConflictUpdate(
              CategoryMapper.toCompanion(dto, tenantId: scope.tenantId, syncedAt: now),
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
      (_db.update(_db.categories)
            ..where((t) =>
                t.tenantId.equals(scope.tenantId) &
                t.id.equals(id) &
                t.isDeleted.equals(false),))
          .write(CategoriesCompanion(
            isDeleted: const Value(true),
            syncedAt: Value(now),
          ),);

  Future<int> _softDeleteMissing(
    MasterScope scope,
    Set<String> present,
    DateTime now,
  ) async {
    final rows = await (_db.select(_db.categories)
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
