import 'package:drift/drift.dart';

/// The last result seen for a given report + filter combination.
///
/// Reports are the one part of the app a manager opens *because* they are
/// standing somewhere without signal — in a stockroom, at a supplier's counter.
/// Showing yesterday's numbers with a visible timestamp is far more useful than
/// an error, provided the staleness is never hidden.
@DataClassName('ReportCacheEntry')
class ReportCacheEntries extends Table {
  /// Report key plus a fingerprint of the filters that produced it. Two date
  /// ranges of the same report are different answers and must not collide.
  TextColumn get cacheKey => text().withLength(min: 1, max: 200)();

  /// The report's own key, so a catalogue change can evict by report.
  TextColumn get reportKey => text().withLength(min: 1, max: 80)();

  /// The raw server payload. Stored verbatim rather than as parsed columns:
  /// the report catalogue is server-driven and a report gains columns without
  /// an app release, so a schema here would go stale by design.
  TextColumn get payload => text()();

  /// When this device received it. Non-null by construction — a cached result
  /// with no timestamp is indistinguishable from a live one, which is the one
  /// way this feature could actively mislead someone.
  DateTimeColumn get fetchedAt => dateTime()();

  @override
  Set<Column> get primaryKey => {cacheKey};
}
