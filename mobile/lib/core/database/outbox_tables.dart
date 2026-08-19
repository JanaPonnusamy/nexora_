import 'package:drift/drift.dart';

/// Writes the user has made that have not reached the server yet.
///
/// Distinct from [SyncQueue], which moves *server-owned* data down to the
/// device and is driven by the sync engine's schedule. This table is the other
/// direction and the other owner: changes a person made, which must not be lost
/// and must arrive in the order they were made.
///
/// Distinct from the capture queue too, which carries whole documents and their
/// image files. An outbox entry is a small mutation of something the server
/// already has.
@DataClassName('OutboxEntry')
class OutboxEntries extends Table {
  IntColumn get id => integer().autoIncrement()();

  /// What to do, e.g. `document.header`. The dispatcher maps this to a call;
  /// features register their own kinds so this table stays feature-agnostic.
  TextColumn get kind => text().withLength(min: 1, max: 64)();

  /// Ordering group, e.g. `import:42`.
  ///
  /// Entries within one scope are applied strictly in order and one at a time:
  /// two edits to the same field must not race, and a line edit that overtook
  /// the header edit before it could be applied against a document in a state
  /// the user never saw. Different scopes are independent and may overlap.
  TextColumn get scope => text().withLength(min: 1, max: 128)();

  /// JSON arguments for the handler.
  TextColumn get payload => text().withDefault(const Constant('{}'))();

  /// pending · inFlight · done · deadLetter
  TextColumn get status =>
      text().withLength(max: 16).withDefault(const Constant('pending'))();

  IntColumn get attemptCount => integer().withDefault(const Constant(0))();

  /// When this may next be attempted. Null means "now".
  DateTimeColumn get nextAttemptAt => dateTime().nullable()();

  /// Why the last attempt failed, shown to the user rather than only logged —
  /// a change that is silently stuck is worse than one that failed loudly.
  TextColumn get lastError => text().nullable()();

  /// Short human-readable description of the change, captured at enqueue time.
  ///
  /// Stored rather than derived because it has to survive: by the time anyone
  /// reads it, the screen that produced it is long gone, and "3 changes waiting"
  /// tells a user nothing about whether it is safe to close the app.
  TextColumn get summary => text().withLength(max: 160).nullable()();

  DateTimeColumn get createdAt => dateTime().withDefault(currentDateAndTime)();
  DateTimeColumn get updatedAt => dateTime().withDefault(currentDateAndTime)();
}
