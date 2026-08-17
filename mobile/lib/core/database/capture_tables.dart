import 'package:drift/drift.dart';

/// Document-capture tables (Phase 2, OCR pipeline).
///
/// The capture queue is the reason capture works offline: a photographed
/// invoice is durable on the device the instant the shutter fires, and the
/// upload is a separate, retryable step. Losing a walked-to-the-warehouse
/// capture because there was no signal is the failure this prevents.

/// One capture batch — a single invoice, which may span several pages.
///
/// The row class is named explicitly: Drift's default singularisation would
/// derive `CaptureBatche` from `CaptureBatches`.
@DataClassName('CaptureBatch')
class CaptureBatches extends Table {
  /// Local id. Distinct from the server's `import_id`, which does not exist
  /// until the upload succeeds.
  IntColumn get id => integer().autoIncrement()();

  /// Server-assigned `doc_import.import_id`, null until uploaded.
  IntColumn get importId => integer().nullable()();

  TextColumn get tenantId => text()();
  TextColumn get storeId => text().nullable()();

  /// Local lifecycle: pending → uploading → uploaded → (server pipeline).
  /// Mirrors DocumentStatus.wire values.
  TextColumn get status =>
      text().withDefault(const Constant('PENDING_UPLOAD'))();

  IntColumn get pageCount => integer().withDefault(const Constant(0))();
  IntColumn get attemptCount => integer().withDefault(const Constant(0))();

  /// Why the last attempt failed, shown on the queue card.
  TextColumn get lastError => text().nullable()();

  /// Earliest time the next attempt may run — backoff, so a queue drain does
  /// not hammer an unreachable server.
  DateTimeColumn get nextAttemptAt => dateTime().nullable()();

  DateTimeColumn get capturedAt => dateTime()();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();

  /// Set once the export has been produced, so the local page images can be
  /// deleted without losing anything the user still needs.
  BoolColumn get isExported => boolean().withDefault(const Constant(false))();
}

/// One captured page image belonging to a [CaptureBatches] row.
class CapturePages extends Table {
  IntColumn get id => integer().autoIncrement()();

  IntColumn get batchId =>
      integer().references(CaptureBatches, #id, onDelete: KeyAction.cascade)();

  /// Absolute path in the app's documents directory.
  TextColumn get filePath => text()();

  /// Page order within the invoice, 1-based.
  IntColumn get pageNumber => integer()();

  IntColumn get byteSize => integer().withDefault(const Constant(0))();

  /// Quality-gate verdict recorded at capture time, so the queue can explain
  /// why a page was flagged without re-analysing the image.
  TextColumn get qualityNote => text().nullable()();

  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
}
