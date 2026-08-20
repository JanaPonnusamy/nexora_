import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/pass_gen/domain/pass_gen_models.dart';
import 'package:nexora_mobile/features/time_report/domain/time_report_models.dart';

/// Phase 4 request/response contracts.
///
/// Both modules encode server-side limits that a client can silently violate:
/// Pass Gen's base-36 ceilings become 422s, and Time Report's query parameter
/// names are aliased on the server. These pin down the wire format.
void main() {
  group('PassGenRequest', () {
    PassGenRequest request({
      int orderNo = 0,
      int minDays = 0,
      int maxDays = 30,
    }) =>
        PassGenRequest(
          orderNo: orderNo,
          targetDate: DateTime(2026, 8, 16),
          minDays: minDays,
          maxDays: maxDays,
        );

    test('serialises the single-row shape the endpoint expects', () {
      final json = request().toJson();

      expect(json['order_no'], 0);
      expect(json['target_date'], '2026-08-16');
      final rows = json['rows'] as List;
      expect(rows, hasLength(1));
      final row = rows.first as Map<String, dynamic>;
      expect(row['min_days'], 0);
      expect(row['max_days'], 30);
      // The server takes 0/1 ints for these, not booleans.
      expect(row['order_yes'], 0);
      expect(row['compare_last_order'], 0);
      expect(row['store_ids'], isEmpty);
    });

    test('flags are sent as ints when enabled', () {
      final json =
          request().copyWith(orderYes: true, compareLastOrder: true).toJson();
      final row = (json['rows'] as List).first as Map<String, dynamic>;

      expect(row['order_yes'], 1);
      expect(row['compare_last_order'], 1);
    });

    test('the day ceiling matches the server base-36 limit', () {
      // MAX_BASE36_2 in passcode.py. Exceeding it is a 422, not a clamp.
      expect(PassGenRequest.maxDays_, 1295);
      expect(request(maxDays: 1295).isValid, isTrue);
      expect(request(maxDays: 1296).isValid, isFalse);
    });

    test('an inverted window is rejected before it reaches the server', () {
      final r = request(minDays: 40, maxDays: 10);
      expect(r.isValid, isFalse);
      expect(r.problem, 'Min days cannot exceed max days.');
    });

    test('order no is capped at 9', () {
      expect(request(orderNo: 9).isValid, isTrue);
      expect(request(orderNo: 10).problem, 'Order No must be 0–9.');
    });

    test('a valid request has nothing to report', () {
      expect(request().problem, isNull);
    });

    test('empty store ids mean every mapped store', () {
      final json = request().toJson();
      expect((json['rows'] as List).first['store_ids'], isEmpty);

      final scoped = request().copyWith(storeIds: ['a', 'b']).toJson();
      expect((scoped['rows'] as List).first['store_ids'], ['a', 'b']);
    });
  });

  group('PassGenStore', () {
    test('an unmapped store cannot produce a passcode', () {
      final store = PassGenStore.fromJson(const {
        'store_id': 's-1',
        'tenant_id': 't-1',
        'store_code': 'NMA',
        'numeric_code': null,
      });

      expect(store.isMapped, isFalse);
      expect(store.label, 'NMA');
    });

    test('a numeric code arriving as a string still maps', () {
      final store = PassGenStore.fromJson(const {
        'store_id': 's-1',
        'tenant_id': 't-1',
        'store_code': 'NMA',
        'store_name': 'Nathan Medicals A',
        'numeric_code': '7',
      });

      expect(store.isMapped, isTrue);
      expect(store.numericCode, 7);
      expect(store.label, 'Nathan Medicals A');
    });
  });

  group('PassGenRowResult', () {
    test('carries skipped store codes so a short result is explainable', () {
      final result = PassGenRowResult.fromJson(const {
        'row_id': 'mobile',
        'results': [
          {
            'store_id': 's-1',
            'store_code': 'NMA',
            'numeric_code': 7,
            'passcode': 'ABCD1234EFGH56',
          },
        ],
        'skipped': ['NMB', 'NMC'],
      });

      expect(result.results, hasLength(1));
      expect(result.results.first.passcode, 'ABCD1234EFGH56');
      expect(result.skipped, ['NMB', 'NMC']);
    });

    test('an empty response parses rather than throwing', () {
      final result = PassGenRowResult.fromJson(const {});
      expect(result.results, isEmpty);
      expect(result.skipped, isEmpty);
    });
  });

  group('TimeReportKind', () {
    test('each report declares only the inputs it reads', () {
      expect(TimeReportKind.daily.needsSingleDate, isTrue);
      expect(TimeReportKind.daily.needsDateRange, isFalse);
      expect(TimeReportKind.misspunch.needsDateRange, isTrue);
      expect(TimeReportKind.user.hasModes, isTrue);
      expect(TimeReportKind.inactive.needsDays, isTrue);
      expect(TimeReportKind.monthly.needsMonth, isTrue);
    });

    test('the tabular reports are the ones sharing a rows shape', () {
      expect(TimeReportKind.misspunch.isTabular, isTrue);
      expect(TimeReportKind.user.isTabular, isTrue);
      expect(TimeReportKind.inactive.isTabular, isTrue);
      // Daily is department-grouped and monthly is a grid.
      expect(TimeReportKind.daily.isTabular, isFalse);
      expect(TimeReportKind.monthly.isTabular, isFalse);
    });

    test('unknown keys resolve to null rather than a wrong report', () {
      expect(TimeReportKind.fromKey('misspunch'), TimeReportKind.misspunch);
      expect(TimeReportKind.fromKey('nope'), isNull);
    });
  });

  group('TimeReportColumns', () {
    test('the user report swaps its column set per mode', () {
      final summary =
          TimeReportColumns.forKind(TimeReportKind.user, summary: true);
      final detail = TimeReportColumns.forKind(TimeReportKind.user);

      expect(summary.map((c) => c.key), contains('present'));
      expect(detail.map((c) => c.key), contains('pdate_str'));
      expect(detail.map((c) => c.key), isNot(contains('present')));
    });

    test('grid-shaped reports have no tabular columns', () {
      expect(TimeReportColumns.forKind(TimeReportKind.monthly), isEmpty);
      expect(TimeReportColumns.forKind(TimeReportKind.daily), isEmpty);
    });
  });

  group('TimeReportFilters', () {
    test('defaults match what each report needs', () {
      final now = DateTime(2026, 8, 16);

      final daily =
          TimeReportFilters.defaultsFor(TimeReportKind.daily, now: now);
      expect(daily.date, now);
      expect(daily.start, isNull);

      final miss =
          TimeReportFilters.defaultsFor(TimeReportKind.misspunch, now: now);
      expect(miss.start, DateTime(2026, 8, 1));
      expect(miss.end, now);

      final monthly =
          TimeReportFilters.defaultsFor(TimeReportKind.monthly, now: now);
      expect(monthly.year, 2026);
      expect(monthly.month, 8);
    });

    test('inactive days default to null so the server decides', () {
      // The server has a configured INACTIVE_DAYS; inventing one here would
      // silently disagree with the desktop console.
      final inactive = TimeReportFilters.defaultsFor(TimeReportKind.inactive);
      expect(inactive.days, isNull);
    });

    test('clearing a department removes it', () {
      const filters = TimeReportFilters(departmentId: '4');
      expect(filters.copyWith(clearDepartment: true).departmentId, isNull);
    });

    test('summary names the filters in force', () {
      final filters = TimeReportFilters(
        start: DateTime(2026, 8, 1),
        end: DateTime(2026, 8, 16),
      );
      expect(
        filters.summary(TimeReportKind.misspunch),
        '01/08 – 16/08',
      );
      expect(
        const TimeReportFilters(summaryMode: true).summary(TimeReportKind.user),
        contains('Summary'),
      );
    });
  });

  group('TimeReportMeta', () {
    test('parses departments and drops report keys it does not know', () {
      final meta = TimeReportMeta.fromJson(const {
        'reports': [
          {'key': 'daily'},
          {'key': 'brand-new-report'},
        ],
        'departments': [
          {'DPTID': 4, 'Name': 'Pharmacy'},
          {'DPTID': 5},
        ],
        'bounds': {'min': '2024-01-01', 'max': '2026-08-16'},
      });

      expect(meta.reports, [TimeReportKind.daily]);
      expect(meta.departments, hasLength(2));
      // DPTID is numeric server-side but must travel as a string.
      expect(meta.departments.first.id, '4');
      expect(meta.departments.first.label, 'Pharmacy');
      expect(meta.departments.last.label, '5');
      expect(meta.minDate, DateTime(2024, 1, 1));
    });

    test('an empty meta parses rather than throwing', () {
      final meta = TimeReportMeta.fromJson(const {});
      expect(meta.reports, isEmpty);
      expect(meta.departments, isEmpty);
      expect(meta.minDate, isNull);
    });
  });

  group('TimeReportResult', () {
    test('derives a count when the server omits one', () {
      final result = TimeReportResult.fromJson(const {
        'rows': [
          {'user_id': '1'},
          {'user_id': '2'},
        ],
      });
      expect(result.count, 2);
      expect(result.isEmpty, isFalse);
    });

    test('an empty result is stamped and empty', () {
      final result = TimeReportResult.fromJson(const {'rows': []});
      expect(result.isEmpty, isTrue);
      expect(result.fetchedAt, isNotNull);
    });
  });

  group('DailyAttendance', () {
    test('groups rows under their department and totals them', () {
      final daily = DailyAttendance.fromJson(const {
        'date_fmt': '16-08-2026',
        'departments': [
          {
            'name': 'Pharmacy',
            'rows': [
              {'user_id': '1'},
              {'user_id': '2'},
            ],
            'totals': {'present': 2},
          },
          {
            'name': 'Admin',
            'rows': [
              {'user_id': '3'},
            ],
          },
        ],
      });

      expect(daily.departments, hasLength(2));
      expect(daily.departments.first.name, 'Pharmacy');
      expect(daily.departments.first.totals['present'], 2);
      expect(daily.totalRows, 3);
      expect(daily.isEmpty, isFalse);
    });

    test('a day with no attendance is empty, not an error', () {
      final daily = DailyAttendance.fromJson(const {'departments': []});
      expect(daily.isEmpty, isTrue);
      expect(daily.totalRows, 0);
    });
  });
}
