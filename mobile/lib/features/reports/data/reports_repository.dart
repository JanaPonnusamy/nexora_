import 'dart:convert';

import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/reports/data/reports_api.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';

/// A report result plus where it came from.
class ReportOutcome {
  const ReportOutcome({required this.result, required this.fromCache});

  final ReportResult result;

  /// True when the server could not be reached and this is the last answer
  /// this device saw. The screen must say so — a stale figure presented as
  /// current is the one way this feature could mislead someone into ordering
  /// against numbers that moved yesterday.
  final bool fromCache;
}

/// Runs reports, and remembers the answers.
///
/// Network-first rather than cache-first: a report is a question about *now*,
/// so a fresh answer always wins when one is available. The cache exists for
/// the case the plan called out — a manager standing in a stockroom with no
/// signal — not to save a round trip.
class ReportsRepository {
  ReportsRepository(this._api, this._db);

  final ReportsApi _api;
  final AppDatabase _db;

  /// Cached results older than this are not served.
  ///
  /// A week-old stock figure is not a useful answer to "what do we have", and
  /// showing one — even stamped — invites someone to act on it. Better to say
  /// the report needs a connection.
  static const Duration maxCacheAge = Duration(days: 2);

  Future<ReportOutcome> run({
    required ReportDef def,
    required String tenantId,
    required String storeId,
    required ReportFilters filters,
    DateTime? now,
  }) async {
    final at = now ?? DateTime.now();
    final key = cacheKeyFor(
      def: def,
      tenantId: tenantId,
      storeId: storeId,
      filters: filters,
    );

    try {
      final result = await _api.run(
        def: def,
        tenantId: tenantId,
        storeId: storeId,
        filters: filters,
      );
      await _store(key, def.key, result, at);
      return ReportOutcome(
        result: result.copyWithFetchedAt(at),
        fromCache: false,
      );
    } on ApiException catch (e) {
      // Only a network failure falls back. A server that rejected the request —
      // a bad filter, an expired session — has given a real answer, and quietly
      // replacing it with yesterday's data would hide the actual problem.
      if (!e.isNetwork) rethrow;

      final cached = await _read(key, at);
      if (cached == null) rethrow;
      return ReportOutcome(result: cached, fromCache: true);
    }
  }

  /// Deterministic identity for one report run.
  ///
  /// The filters are part of the key: the same report over two date ranges is
  /// two different answers, and collapsing them would serve one as the other.
  /// Store and tenant too — a user who switches store must not see the previous
  /// store's numbers.
  static String cacheKeyFor({
    required ReportDef def,
    required String tenantId,
    required String storeId,
    required ReportFilters filters,
  }) {
    final parts = <String, String>{
      'report': def.key,
      'tenant': tenantId,
      'store': storeId,
      if (def.needsDateRange) 'from': _date(filters.from),
      if (def.needsDateRange) 'to': _date(filters.to),
      if (def.needsDwellDays) 'dwell': '${filters.dwellDays ?? ''}',
      if (def.needsSupplier) 'supplier': filters.supplierCode ?? '',
      if (def.needsDivision) 'division': filters.divisionCode ?? '',
    };
    // Sorted so an unordered map cannot produce two keys for one query.
    final sorted = parts.keys.toList()..sort();
    return sorted.map((k) => '$k=${parts[k]}').join('&');
  }

  static String _date(DateTime? value) => value == null
      ? ''
      : '${value.year.toString().padLeft(4, '0')}-'
          '${value.month.toString().padLeft(2, '0')}-'
          '${value.day.toString().padLeft(2, '0')}';

  Future<void> _store(
    String key,
    String reportKey,
    ReportResult result,
    DateTime at,
  ) async {
    await _db.into(_db.reportCacheEntries).insertOnConflictUpdate(
          ReportCacheEntriesCompanion.insert(
            cacheKey: key,
            reportKey: reportKey,
            payload: jsonEncode(result.toCacheJson()),
            fetchedAt: at,
          ),
        );
  }

  Future<ReportResult?> _read(String key, DateTime at) async {
    final row = await (_db.select(_db.reportCacheEntries)
          ..where((t) => t.cacheKey.equals(key)))
        .getSingleOrNull();
    if (row == null) return null;
    if (at.difference(row.fetchedAt) > maxCacheAge) return null;

    try {
      final decoded = jsonDecode(row.payload);
      if (decoded is! Map<String, dynamic>) return null;
      return ReportResult.fromJson(decoded, fetchedAt: row.fetchedAt);
    } on FormatException {
      // A payload written by an older build that no longer parses is not worth
      // failing the request over — it is treated as a cache miss.
      return null;
    }
  }

  /// Drops cached results past [maxCacheAge]. Called on sign-out and by the
  /// storage housekeeping in Settings.
  Future<int> prune({DateTime? now}) {
    final cutoff = (now ?? DateTime.now()).subtract(maxCacheAge);
    return (_db.delete(_db.reportCacheEntries)
          ..where((t) => t.fetchedAt.isSmallerThanValue(cutoff)))
        .go();
  }

  /// Wipes everything. Used when the active store changes, so one store's
  /// numbers can never surface under another's name.
  Future<int> clear() => _db.delete(_db.reportCacheEntries).go();
}
