import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/reports/domain/report_formatting.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';

/// The reports module is metadata-driven: the whole UI is generated from the
/// catalog entry and the response envelope. That makes this parsing and
/// formatting layer the place where a server change would silently produce a
/// wrong-looking report, so it is pinned down here.
void main() {
  group('ReportDef', () {
    test('reads the input flags the catalog publishes', () {
      final def = ReportDef.fromJson(const {
        'key': 'non-moving',
        'label': 'Non Moving',
        'group': 'Stock',
        'needs_dwell_days': true,
        'needs_supplier': true,
      });

      expect(def.needsDwellDays, isTrue);
      expect(def.needsSupplier, isTrue);
      expect(def.needsDateRange, isFalse);
      // Supplier is a filter, not a requirement — it must not force a prompt.
      expect(def.runsImmediately, isFalse);
    });

    test('a report with no required inputs runs on arrival', () {
      final def = ReportDef.fromJson(const {
        'key': 'x',
        'label': 'X',
        'group': 'Sales',
      });
      expect(def.runsImmediately, isTrue);
    });

    test('a supplier-only report still runs without being asked anything', () {
      final def = ReportDef.fromJson(const {
        'key': 'y',
        'label': 'Y',
        'group': 'Stock',
        'needs_supplier': true,
      });
      expect(def.runsImmediately, isTrue);
    });

    test('falls back to the key when the server omits a label', () {
      expect(ReportDef.fromJson(const {'key': 'margin'}).label, 'margin');
    });
  });

  group('ReportFilters', () {
    final def = ReportDef.fromJson(const {
      'key': 'margin',
      'label': 'Margin',
      'group': 'Margin',
      'needs_date_range': true,
    });

    test('defaults to the current month to date', () {
      final filters = ReportFilters.defaultsFor(
        def,
        now: DateTime(2026, 8, 16),
      );

      expect(filters.from, DateTime(2026, 8, 1));
      expect(filters.to, DateTime(2026, 8, 16));
    });

    test('a report needing nothing gets no defaults', () {
      final plain = ReportDef.fromJson(const {'key': 'x', 'label': 'X'});
      final filters = ReportFilters.defaultsFor(plain);

      expect(filters.from, isNull);
      expect(filters.dwellDays, isNull);
    });

    test('dwell reports default to 120 days', () {
      final dwell = ReportDef.fromJson(const {
        'key': 'non-moving',
        'label': 'Non Moving',
        'needs_dwell_days': true,
      });
      expect(ReportFilters.defaultsFor(dwell).dwellDays, 120);
    });

    test('satisfies only when every required input is present', () {
      expect(const ReportFilters().satisfies(def), isFalse);
      expect(
        ReportFilters(from: DateTime(2026, 8, 1), to: DateTime(2026, 8, 16))
            .satisfies(def),
        isTrue,
      );
    });

    test('a missing supplier never blocks a run', () {
      final withSupplier = ReportDef.fromJson(const {
        'key': 'non-moving',
        'label': 'Non Moving',
        'needs_dwell_days': true,
        'needs_supplier': true,
      });
      expect(
          const ReportFilters(dwellDays: 90).satisfies(withSupplier), isTrue);
    });

    test('clearing the supplier removes both code and name', () {
      const filters = ReportFilters(
        supplierCode: 'S1',
        supplierName: 'Acme',
        dwellDays: 90,
      );
      final cleared = filters.copyWith(clearSupplier: true);

      expect(cleared.supplierCode, isNull);
      expect(cleared.supplierName, isNull);
      // Unrelated fields survive.
      expect(cleared.dwellDays, 90);
    });

    test('summary names the filters actually in force', () {
      final filters = ReportFilters(
        from: DateTime(2026, 8, 1),
        to: DateTime(2026, 8, 16),
      );
      expect(filters.summary(def), '01/08 – 16/08');
      expect(const ReportFilters().summary(def), 'No filters');
    });
  });

  group('ReportResult', () {
    ReportResult result() => ReportResult.fromJson(const {
          'report': 'non-moving',
          'title': 'Non Moving',
          'columns': [
            {'key': 'ProductName', 'label': 'Product', 'align': 'left'},
            {
              'key': 'TotalStock',
              'label': 'Stock',
              'align': 'right',
              'format': 'int',
            },
            {
              'key': 'MRP',
              'label': 'MRP',
              'align': 'right',
              'format': 'money',
            },
          ],
          'rows': [
            {'ProductName': 'Paracetamol', 'TotalStock': '40', 'MRP': '12.50'},
          ],
          'summary': {'TotalStock': 40, 'Ignored': 99},
        });

    test('leads each card with the first non-numeric column', () {
      expect(result().primaryColumn?.key, 'ProductName');
      expect(
        result().detailColumns.map((c) => c.key),
        ['TotalStock', 'MRP'],
      );
    });

    test('numeric columns are recognised for alignment and weight', () {
      final columns = result().columns;
      expect(columns[0].isNumeric, isFalse);
      expect(columns[1].isNumeric, isTrue);
      expect(columns[2].format, ReportFormat.money);
      expect(columns[1].align, ReportAlign.right);
    });

    test('a result is always stamped with when it arrived', () {
      expect(result().fetchedAt, isNotNull);
    });

    test('an empty response parses rather than throwing', () {
      final empty = ReportResult.fromJson(const {});
      expect(empty.isEmpty, isTrue);
      expect(empty.columns, isEmpty);
      expect(empty.primaryColumn, isNull);
    });
  });

  group('ReportFormatter', () {
    const money = ReportColumn(
      key: 'x',
      label: 'X',
      format: ReportFormat.money,
    );
    const count = ReportColumn(key: 'x', label: 'X', format: ReportFormat.int_);
    const day = ReportColumn(key: 'x', label: 'X', format: ReportFormat.date);

    test('parses the Decimal-as-string the API actually sends', () {
      // FastAPI serialises SQL Decimal as a string; formatting has to parse
      // before it can format or every money column shows raw.
      expect(ReportFormatter.cell('1234.5', money), '1,234.50');
      expect(ReportFormatter.cell('4000', count), '4,000');
    });

    test('groups thousands and keeps two decimals for money', () {
      expect(ReportFormatter.cell(1234567.891, money), '1,234,567.89');
      expect(ReportFormatter.cell(-1234.5, money), '-1,234.50');
      expect(ReportFormatter.cell(12, money), '12.00');
    });

    test('an unparseable value is shown raw, not blanked', () {
      // A number the app cannot parse is still information; an empty cell
      // reads as missing data.
      expect(ReportFormatter.cell('N/A', money), 'N/A');
    });

    test('null renders as an em dash rather than empty space', () {
      expect(ReportFormatter.cell(null, money), '—');
      expect(ReportFormatter.cell(null, day), '—');
    });

    test('dates render compactly but keep the year', () {
      expect(ReportFormatter.cell('2026-08-16T00:00:00', day), '16 Aug 26');
      expect(ReportFormatter.cell('2026-01-05', day), '05 Jan 26');
    });

    test('an unparseable date falls through to the raw string', () {
      expect(ReportFormatter.cell('not a date', day), 'not a date');
    });

    test('compact form for the summary strip', () {
      expect(ReportFormatter.compact(950), '950');
      expect(ReportFormatter.compact(1500), '1.5k');
      expect(ReportFormatter.compact(2400000), '2.4M');
    });
  });

  group('reportToCsv', () {
    test('writes the header and every row in column order', () {
      final result = ReportResult.fromJson(const {
        'columns': [
          {'key': 'a', 'label': 'Product'},
          {'key': 'b', 'label': 'Qty'},
        ],
        'rows': [
          {'a': 'Paracetamol', 'b': 40},
          {'a': 'Ibuprofen', 'b': 12},
        ],
      });

      final csv = reportToCsv(result);
      expect(csv, contains('Product,Qty'));
      expect(csv, contains('Paracetamol,40'));
      expect(csv, contains('Ibuprofen,12'));
    });

    test('quotes values containing commas and quotes', () {
      // Product names in this catalog contain commas routinely; an unquoted
      // CSV would silently shift every column after them.
      final result = ReportResult.fromJson(const {
        'columns': [
          {'key': 'a', 'label': 'Product'},
        ],
        'rows': [
          {'a': 'Tablet, 500mg'},
          {'a': 'He said "hi"'},
        ],
      });

      final csv = reportToCsv(result);
      expect(csv, contains('"Tablet, 500mg"'));
      expect(csv, contains('"He said ""hi"""'));
    });

    test('a missing cell becomes an empty field, not the word null', () {
      final result = ReportResult.fromJson(const {
        'columns': [
          {'key': 'a', 'label': 'A'},
          {'key': 'b', 'label': 'B'},
        ],
        'rows': [
          {'a': 'x'},
        ],
      });

      expect(reportToCsv(result), contains('x,\n'));
    });
  });
}
