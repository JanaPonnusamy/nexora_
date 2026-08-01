import 'dart:io';

import 'package:drift/drift.dart';
import 'package:drift/native.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqlite3_flutter_libs/sqlite3_flutter_libs.dart';

part 'app_database.g.dart';

/// Simple durable key/value cache. Phase 1 only needs a foundation for local
/// persistence; the real sync tables (products, stock, procurement, …) arrive
/// in Phase 2 as additional Drift tables in this database.
class AppKeyValue extends Table {
  TextColumn get key => text()();
  TextColumn get value => text()();
  DateTimeColumn get updatedAt =>
      dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {key};
}

@DriftDatabase(tables: [AppKeyValue])
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(_open());

  /// Test/override constructor.
  AppDatabase.withExecutor(super.executor);

  @override
  int get schemaVersion => 1;

  Future<void> put(String key, String value) => into(appKeyValue).insertOnConflictUpdate(
        AppKeyValueCompanion.insert(key: key, value: value),
      );

  Future<String?> get(String key) async {
    final row = await (select(appKeyValue)..where((t) => t.key.equals(key)))
        .getSingleOrNull();
    return row?.value;
  }

  static LazyDatabase _open() {
    return LazyDatabase(() async {
      final dir = await getApplicationDocumentsDirectory();
      final file = File(p.join(dir.path, 'nexora.sqlite'));
      // Ensures the bundled sqlite3 is used on all platforms.
      await applyWorkaroundToOpenSqlite3OnOldAndroidVersions();
      return NativeDatabase.createInBackground(file);
    });
  }
}
