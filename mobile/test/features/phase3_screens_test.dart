import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/master_data/application/supplier_providers.dart';
import 'package:nexora_mobile/features/master_data/domain/supplier.dart';
import 'package:nexora_mobile/features/master_data/presentation/suppliers_screen.dart';
import 'package:nexora_mobile/features/reports/application/reports_providers.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';
import 'package:nexora_mobile/features/reports/presentation/reports_catalog_screen.dart';
import 'package:nexora_mobile/features/reports/presentation/widgets/report_row_card.dart';
import 'package:nexora_mobile/features/sync/data/sync_live_models.dart';
import 'package:nexora_mobile/features/sync/presentation/widgets/live_execution_card.dart';

/// Paint-pass coverage for the Phase 3 screens.
///
/// Every one of these puts themed buttons inside a Row or Wrap, which is the
/// exact shape that asserted on an infinite width earlier in this project and
/// sailed through `analyze`. Nothing here is trusted without rendering it.
void main() {
  Widget host(Widget child, {List<Override> overrides = const []}) {
    return ProviderScope(
      overrides: overrides,
      child: MaterialApp(theme: AppTheme.dark, home: child),
    );
  }

  group('LiveExecutionCard', () {
    LiveSyncExecution execution({
      String status = 'RUNNING',
      int? total = 10000,
      String? table = 'dbo.Products',
    }) =>
        LiveSyncExecution.fromJson({
          'store_id': 's-1',
          'store_name': 'Nathan Medicals A',
          'execution_id': 'e-1',
          'status': status,
          'sync_type': 'DELTA',
          'current_table': table,
          'execution_rows_processed': 2500,
          'execution_total_rows': total,
          'speed_rows_sec': 42.0,
          'eta_seconds': 120,
          'started_at': DateTime.now()
              .subtract(const Duration(minutes: 3))
              .toIso8601String(),
        });

    testWidgets('a running execution shows progress and both controls',
        (tester) async {
      await tester.pumpWidget(
        host(
          Scaffold(
            body: LiveExecutionCard(
              execution: execution(),
              onControl: (_) {},
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('Nathan Medicals A'), findsOneWidget);
      expect(find.text('Syncing'), findsOneWidget);
      expect(find.text('Pause'), findsOneWidget);
      expect(find.text('Stop'), findsOneWidget);
      expect(find.textContaining('25%'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a paused execution cannot be paused again', (tester) async {
      await tester.pumpWidget(
        host(
          Scaffold(
            body: LiveExecutionCard(
              execution: execution(status: 'PAUSED'),
              onControl: (_) {},
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('Paused'), findsOneWidget);
      expect(find.text('Pause'), findsNothing);
      expect(find.text('Stop'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an execution with no totals still renders', (tester) async {
      // Indeterminate bar — this is the common state in the first seconds of a
      // run, before the agent reports totals.
      await tester.pumpWidget(
        host(
          Scaffold(
            body: LiveExecutionCard(
              execution: execution(total: null, table: null),
              onControl: (_) {},
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.textContaining('rows sent'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the control callback reports which action was tapped',
        (tester) async {
      final actions = <SyncControlAction>[];
      await tester.pumpWidget(
        host(
          Scaffold(
            body: LiveExecutionCard(
              execution: execution(),
              onControl: actions.add,
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('Pause'));
      await tester.pump();
      expect(actions, [SyncControlAction.pause]);
    });
  });

  group('ReportsCatalogScreen', () {
    testWidgets('groups the catalog and says what each report needs',
        (tester) async {
      await tester.pumpWidget(
        host(
          const ReportsCatalogScreen(),
          overrides: [
            reportScopeProvider.overrideWithValue(
              const ReportScope(tenantId: 't-1', storeId: 's-1'),
            ),
            reportCatalogProvider.overrideWith(
              (_) async => [
                ReportDef.fromJson(const {
                  'key': 'margin',
                  'label': 'Margin',
                  'group': 'Margin',
                  'needs_date_range': true,
                }),
                ReportDef.fromJson(const {
                  'key': 'non-moving',
                  'label': 'Non Moving',
                  'group': 'Stock',
                  'needs_dwell_days': true,
                  'needs_supplier': true,
                }),
              ],
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('MARGIN'), findsOneWidget);
      expect(find.text('STOCK'), findsOneWidget);
      expect(find.text('Margin'), findsOneWidget);
      expect(find.text('Needs date range'), findsOneWidget);
      expect(
        find.text('Needs idle days, supplier (optional)'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('without a store it explains rather than failing',
        (tester) async {
      await tester.pumpWidget(
        host(
          const ReportsCatalogScreen(),
          overrides: [reportScopeProvider.overrideWithValue(null)],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('scoped to a store'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('ReportRowCard', () {
    testWidgets('renders a row as a labelled card, formatted per column',
        (tester) async {
      final result = ReportResult.fromJson(const {
        'columns': [
          {'key': 'ProductName', 'label': 'Product'},
          {'key': 'MRP', 'label': 'MRP', 'format': 'money'},
          {'key': 'Expiry', 'label': 'Expiry', 'format': 'date'},
        ],
        'rows': [
          {
            'ProductName': 'Paracetamol 500mg',
            'MRP': '12.5',
            'Expiry': '2027-03-01',
          },
        ],
      });

      await tester.pumpWidget(
        host(
          Scaffold(
            body: ReportRowCard(
              row: result.rows.first,
              result: result,
              index: 0,
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('Paracetamol 500mg'), findsOneWidget);
      expect(find.text('12.50'), findsOneWidget);
      expect(find.text('01 Mar 27'), findsOneWidget);
      expect(find.text('#1'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a summary showing only real columns renders', (tester) async {
      final result = ReportResult.fromJson(const {
        'columns': [
          {'key': 'a', 'label': 'Stock', 'format': 'int'},
        ],
        'rows': [],
        'summary': {'a': 4000, 'internal_only': 1},
      });

      await tester.pumpWidget(
        host(Scaffold(body: ReportSummaryCard(result: result))),
      );
      await tester.pump();

      expect(find.text('TOTALS'), findsOneWidget);
      expect(find.text('4,000'), findsOneWidget);
      expect(find.text('1'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  group('SuppliersScreen', () {
    Supplier supplier(String name, {int products = 10, double stock = 500}) =>
        Supplier(
          tenantId: 't-1',
          storeId: 's-1',
          supplierCode: name.substring(0, 3).toUpperCase(),
          supplierName: name,
          productCount: products,
          availableCount: products ~/ 2,
          totalAvailableStock: stock,
          syncedAt: DateTime.now().subtract(const Duration(minutes: 5)),
        );

    testWidgets('lists cached suppliers with a sync stamp', (tester) async {
      await tester.pumpWidget(
        host(
          const SuppliersScreen(),
          overrides: [
            supplierListProvider.overrideWith(
              (_) => Stream.value([supplier('Acme Pharma'), supplier('Beta')]),
            ),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Acme Pharma'), findsOneWidget);
      expect(find.text('2 suppliers'), findsOneWidget);
      // A cached list is only trustworthy if it says how old it is.
      expect(find.textContaining('Synced'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an empty cache points at sync rather than looking broken',
        (tester) async {
      await tester.pumpWidget(
        host(
          const SuppliersScreen(),
          overrides: [
            supplierListProvider.overrideWith((_) => Stream.value(const [])),
          ],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.textContaining('Pull down to sync'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}
