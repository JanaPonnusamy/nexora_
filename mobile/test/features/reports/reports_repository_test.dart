import 'package:dio/dio.dart';
import 'package:drift/drift.dart' show DatabaseConnection;
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/reports/data/reports_api.dart';
import 'package:nexora_mobile/features/reports/data/reports_repository.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';

final _unusedDio = Dio();

class _FakeReportsApi extends ReportsApi {
  _FakeReportsApi() : super(_unusedDio);

  ApiException? error;
  int calls = 0;
  List<Map<String, dynamic>> rows = [
    {'product': 'PARACETAMOL 500MG', 'qty': 100},
  ];

  @override
  Future<ReportResult> run({
    required ReportDef def,
    required String tenantId,
    required String storeId,
    required ReportFilters filters,
  }) async {
    calls++;
    if (error != null) throw error!;
    return ReportResult(
      report: def.key,
      title: def.label,
      columns: const [
        ReportColumn(key: 'product', label: 'Product'),
        ReportColumn(
          key: 'qty',
          label: 'Qty',
          align: ReportAlign.right,
          format: ReportFormat.int_,
        ),
      ],
      rows: rows,
    );
  }
}

const _def = ReportDef(
  key: 'stock-on-hand',
  label: 'Stock on hand',
  group: 'Stock',
);

const _offline = ApiException(message: 'No connection.', isNetwork: true);
const _rejected = ApiException(message: 'Session expired.', statusCode: 401);

void main() {
  late AppDatabase db;
  late _FakeReportsApi api;
  late ReportsRepository repo;

  setUp(() {
    db = AppDatabase.withExecutor(DatabaseConnection(NativeDatabase.memory()));
    api = _FakeReportsApi();
    repo = ReportsRepository(api, db);
  });

  tearDown(() => db.close());

  Future<ReportOutcome> run({DateTime? now, ReportFilters? filters}) =>
      repo.run(
        def: _def,
        tenantId: 't-1',
        storeId: 's-1',
        filters: filters ?? const ReportFilters(),
        now: now,
      );

  test('a live run is served from the server and stamped', () async {
    final at = DateTime(2026, 8, 18, 9);

    final outcome = await run(now: at);

    expect(outcome.fromCache, isFalse);
    expect(outcome.result.rows.single['product'], 'PARACETAMOL 500MG');
    expect(outcome.result.fetchedAt, at);
  });

  test('offline falls back to the last answer, marked as cached', () async {
    final first = DateTime(2026, 8, 18, 9);
    await run(now: first);

    api.error = _offline;
    final outcome = await run(now: first.add(const Duration(hours: 1)));

    expect(outcome.fromCache, isTrue);
    expect(outcome.result.rows.single['product'], 'PARACETAMOL 500MG');
    expect(outcome.result.fetchedAt, first,
        reason: 'the stamp must be when the data was fetched, not read');
  });

  test('the round trip preserves column formatting', () async {
    final at = DateTime(2026, 8, 18, 9);
    await run(now: at);

    api.error = _offline;
    final outcome = await run(now: at.add(const Duration(minutes: 5)));

    final qty = outcome.result.columns.last;
    expect(qty.key, 'qty');
    expect(qty.format, ReportFormat.int_,
        reason: 'int_ must round-trip as the wire spelling "int"');
    expect(qty.align, ReportAlign.right);
  });

  test(
    'a server refusal is not replaced by cached data — hiding a 401 behind '
    'yesterday\'s numbers hides the real problem',
    () async {
      final at = DateTime(2026, 8, 18, 9);
      await run(now: at);

      api.error = _rejected;

      expect(
        () => run(now: at.add(const Duration(minutes: 5))),
        throwsA(isA<ApiException>()),
      );
    },
  );

  test('offline with nothing cached rethrows rather than inventing an answer',
      () async {
    api.error = _offline;

    expect(() => run(), throwsA(isA<ApiException>()));
  });

  test('a cached answer past its shelf life is not served', () async {
    final at = DateTime(2026, 8, 18, 9);
    await run(now: at);

    api.error = _offline;
    final stale =
        at.add(ReportsRepository.maxCacheAge + const Duration(hours: 1));

    expect(() => run(now: stale), throwsA(isA<ApiException>()),
        reason:
            'a week-old stock figure is not an answer to "what do we have"');
  });

  group('cache key', () {
    String keyFor(ReportFilters filters, {String storeId = 's-1'}) =>
        ReportsRepository.cacheKeyFor(
          def: const ReportDef(
            key: 'sales',
            label: 'Sales',
            group: 'Sales',
            needsDateRange: true,
          ),
          tenantId: 't-1',
          storeId: storeId,
          filters: filters,
        );

    test('two date ranges of one report are different answers', () {
      final a = keyFor(
        ReportFilters(from: DateTime(2026, 8, 1), to: DateTime(2026, 8, 7)),
      );
      final b = keyFor(
        ReportFilters(from: DateTime(2026, 8, 8), to: DateTime(2026, 8, 14)),
      );

      expect(a, isNot(b));
    });

    test('a different store never reads the previous store\'s numbers', () {
      final a = keyFor(const ReportFilters(), storeId: 's-1');
      final b = keyFor(const ReportFilters(), storeId: 's-2');

      expect(a, isNot(b));
    });

    test('the same query produces the same key', () {
      final filters = ReportFilters(
        from: DateTime(2026, 8, 1),
        to: DateTime(2026, 8, 7),
      );

      expect(keyFor(filters), keyFor(filters));
    });

    test('a filter the report does not declare is not part of its key', () {
      // Otherwise a stale supplier selection left in the sheet would split the
      // cache for a report that never sends it.
      final a = keyFor(const ReportFilters(supplierCode: 'SUP-1'));
      final b = keyFor(const ReportFilters(supplierCode: 'SUP-2'));

      expect(a, b);
    });
  });

  test('prune drops only what is past the shelf life', () async {
    final at = DateTime(2026, 8, 18, 9);
    await run(now: at);

    expect(await repo.prune(now: at), 0);
    expect(
      await repo.prune(now: at.add(ReportsRepository.maxCacheAge * 2)),
      1,
    );
  });

  test('clear wipes everything, for a store switch', () async {
    await run(now: DateTime(2026, 8, 18, 9));

    expect(await repo.clear(), 1);
  });
}
