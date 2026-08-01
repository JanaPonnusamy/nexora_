import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/connection/connection.dart';
import 'package:nexora_mobile/core/database/tables.dart';

part 'app_database.g.dart';

/// Simple durable key/value cache carried over from Phase 1.
class AppKeyValue extends Table {
  TextColumn get key => text()();
  TextColumn get value => text()();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {key};
}

/// The application's local database.
///
/// Schema v2 adds the synchronization-infrastructure tables (see `tables.dart`)
/// for the Phase 2 store agent and Phase 3 sync engine. No business tables are
/// present yet.
@DriftDatabase(
  tables: [
    AppKeyValue,
    DeviceInformation,
    SyncMetadata,
    SyncConfiguration,
    SyncState,
    SyncQueue,
    SyncHistory,
  ],
)
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(openDatabaseConnection());

  /// Test/override constructor.
  AppDatabase.withExecutor(super.executor);

  @override
  int get schemaVersion => 2;

  @override
  MigrationStrategy get migration => MigrationStrategy(
        onCreate: (m) async {
          await m.createAll();
        },
        onUpgrade: (m, from, to) async {
          if (from < 2) {
            // v1 → v2: add sync infrastructure tables. AppKeyValue already
            // exists from v1 and is left untouched.
            await m.createTable(deviceInformation);
            await m.createTable(syncMetadata);
            await m.createTable(syncConfiguration);
            await m.createTable(syncState);
            await m.createTable(syncQueue);
            await m.createTable(syncHistory);
          }
        },
        beforeOpen: (details) async {
          await customStatement('PRAGMA foreign_keys = ON');
        },
      );

  // --- Legacy key/value helpers (unchanged) --------------------------------

  Future<void> put(String key, String value) =>
      into(appKeyValue).insertOnConflictUpdate(
        AppKeyValueCompanion.insert(key: key, value: value),
      );

  Future<String?> get(String key) async {
    final row = await (select(appKeyValue)..where((t) => t.key.equals(key)))
        .getSingleOrNull();
    return row?.value;
  }
}
