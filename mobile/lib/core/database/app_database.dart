import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/capture_tables.dart';
import 'package:nexora_mobile/core/database/connection/connection.dart';
import 'package:nexora_mobile/core/database/master_data_tables.dart';
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
/// for the Phase 2 store agent and Phase 3 sync engine. Schema v3 (Phase 4) adds
/// the offline business **master-data** tables (see `master_data_tables.dart`) —
/// reference data only, no transactional tables.
@DriftDatabase(
  tables: [
    AppKeyValue,
    DeviceInformation,
    SyncMetadata,
    SyncConfiguration,
    SyncState,
    SyncQueue,
    SyncHistory,
    // Phase 4 — business master data.
    Departments,
    Categories,
    Manufacturers,
    Units,
    TaxMaster,
    Suppliers,
    // Phase 2 (OCR) — offline document capture queue.
    CaptureBatches,
    CapturePages,
  ],
)
class AppDatabase extends _$AppDatabase {
  AppDatabase() : super(openDatabaseConnection());

  /// Test/override constructor.
  AppDatabase.withExecutor(super.executor);

  @override
  int get schemaVersion => 4;

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
          if (from < 3) {
            // v2 → v3: add Phase 4 master-data tables.
            await m.createTable(departments);
            await m.createTable(categories);
            await m.createTable(manufacturers);
            await m.createTable(units);
            await m.createTable(taxMaster);
            await m.createTable(suppliers);
          }
          if (from < 4) {
            // v3 → v4: add the offline document-capture queue.
            await m.createTable(captureBatches);
            await m.createTable(capturePages);
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
