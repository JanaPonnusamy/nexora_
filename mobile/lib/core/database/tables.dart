import 'package:drift/drift.dart';

/// Synchronization-infrastructure tables.
///
/// Phase 2/3 only add tables that support the Legacy Store Agent and the sync
/// engine. NO business tables (products, stock, procurement, …) are created
/// here — those arrive with their modules in later phases.

/// Durable identity + metadata for this installation. Single row (id == 1).
/// Populated once on first launch and refreshed on every startup so the
/// registration survives restarts and the Device Status screen can read it
/// offline.
class DeviceInformation extends Table {
  IntColumn get id => integer().withDefault(const Constant(1))();
  TextColumn get deviceId => text()();
  TextColumn get platform => text()();
  TextColumn get model => text().withDefault(const Constant(''))();
  TextColumn get osVersion => text().withDefault(const Constant(''))();
  TextColumn get appVersion => text().withDefault(const Constant(''))();
  TextColumn get buildNumber => text().withDefault(const Constant(''))();
  DateTimeColumn get registeredAt => dateTime()();
  DateTimeColumn get lastSeenAt => dateTime()();

  @override
  Set<Column> get primaryKey => {id};
}

/// Per-entity synchronization bookkeeping: the delta watermark (server cursor),
/// the last successful sync time and the last observed status. One row per
/// logical entity (e.g. `store_config`, `sync_table_master`).
class SyncMetadata extends Table {
  TextColumn get entity => text()();

  /// Opaque server cursor for delta pulls (e.g. an ISO timestamp or row
  /// version). `null` means a full pull has never completed.
  TextColumn get watermark => text().nullable()();
  DateTimeColumn get lastSyncAt => dateTime().nullable()();
  TextColumn get lastStatus => text().withDefault(const Constant('never'))();
  IntColumn get recordCount => integer().withDefault(const Constant(0))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {entity};
}

/// Cached configuration blobs (store record, sync table metadata, agent
/// settings) keyed by a stable name. Values are JSON so the schema does not
/// churn as config shapes evolve. This is what makes configuration survive an
/// application restart and be available fully offline.
class SyncConfiguration extends Table {
  TextColumn get key => text()();
  TextColumn get value => text()();
  IntColumn get version => integer().withDefault(const Constant(0))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {key};
}

/// Persisted engine state so a sync that was interrupted (app killed, device
/// slept, network lost) can be understood and resumed on next launch. Single
/// row (id == 1).
class SyncState extends Table {
  IntColumn get id => integer().withDefault(const Constant(1))();
  TextColumn get status => text().withDefault(const Constant('idle'))();
  DateTimeColumn get lastRunAt => dateTime().nullable()();
  DateTimeColumn get lastSuccessAt => dateTime().nullable()();
  TextColumn get lastError => text().nullable()();
  IntColumn get pendingCount => integer().withDefault(const Constant(0))();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {id};
}

/// The unified operation queue. It backs the upload, download, retry and
/// offline queues at once — those are simply views over rows filtered by
/// [direction] and [status]. Rows survive restarts, so work queued while
/// offline resumes automatically when connectivity returns.
class SyncQueue extends Table {
  IntColumn get id => integer().autoIncrement()();

  /// `download` (pull from backend) or `upload` (push to backend).
  TextColumn get direction => text()();

  /// Logical target, e.g. `store_config`, `sync_table_master`.
  TextColumn get entity => text()();

  /// `pull`, `create`, `update`, `delete`.
  TextColumn get operation => text()();

  /// JSON payload for uploads / pull parameters. Empty object for simple pulls.
  TextColumn get payload => text().withDefault(const Constant('{}'))();

  /// `pending`, `inFlight`, `failed`, `done`, `deadLetter`.
  TextColumn get status => text().withDefault(const Constant('pending'))();
  IntColumn get attempts => integer().withDefault(const Constant(0))();
  IntColumn get maxAttempts => integer().withDefault(const Constant(5))();

  /// When the retry queue may next pick this row up (exponential backoff).
  DateTimeColumn get nextAttemptAt => dateTime().nullable()();
  TextColumn get lastError => text().nullable()();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
}

/// Append-only sync log / history. Powers the Sync Status screen's activity
/// feed and post-hoc diagnostics. Trimmed to a bounded size by the logger.
class SyncHistory extends Table {
  IntColumn get id => integer().autoIncrement()();

  /// `fine`, `info`, `warning`, `error`.
  TextColumn get level => text().withDefault(const Constant('info'))();

  /// Grouping tag, e.g. `queue`, `delta`, `connectivity`, `config`.
  TextColumn get category => text().withDefault(const Constant('sync'))();
  TextColumn get entity => text().nullable()();
  TextColumn get message => text()();
  TextColumn get detail => text().nullable()();
  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
}
