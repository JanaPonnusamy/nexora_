import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/procurement/application/purchase_workspace_providers.dart';
import 'package:nexora_mobile/features/procurement/application/refresh_compare_providers.dart';
import 'package:nexora_mobile/features/procurement/application/stock_distribution_providers.dart';
import 'package:nexora_mobile/features/procurement/domain/cycle_models.dart';
import 'package:nexora_mobile/features/procurement/domain/refresh_compare_models.dart';
import 'package:nexora_mobile/features/procurement/domain/stock_distribution_models.dart';
import 'package:nexora_mobile/features/procurement/presentation/procurement_conflicts_screen.dart';
import 'package:nexora_mobile/features/procurement/presentation/refresh_compare_screen.dart';
import 'package:nexora_mobile/features/procurement/presentation/stock_distribution_screen.dart';

Widget _app(Widget child, List<Override> overrides) => ProviderScope(
      overrides: [isOnlineProvider.overrideWith((ref) => true), ...overrides],
      child: MaterialApp(theme: AppTheme.dark, home: child),
    );

void main() {
  testWidgets('Refresh Compare offers two refreshes from the same cycle',
      (tester) async {
    const cycle = ProcurementCycle(
      cycleId: 'cycle-1',
      name: 'August cycle',
      status: CycleStatus.active,
      rawStatus: 'ACTIVE',
    );
    const refreshes = [
      ProcurementRefresh(
        refreshId: 'refresh-2',
        cycleId: 'cycle-1',
        name: 'Second',
        number: 2,
        status: 'Ready',
      ),
      ProcurementRefresh(
        refreshId: 'refresh-1',
        cycleId: 'cycle-1',
        name: 'First',
        number: 1,
        status: 'Archived',
      ),
    ];
    await tester.pumpWidget(_app(const RefreshCompareScreen(), [
      refreshCompareSetupProvider.overrideWith(
        (ref) async =>
            const RefreshCompareSetup(cycles: [cycle], refreshes: refreshes),
      ),
    ]));
    await tester.pumpAndSettle();

    expect(find.text('August cycle'), findsOneWidget);
    expect(find.textContaining('Refresh 1'), findsOneWidget);
    expect(find.textContaining('Refresh 2'), findsOneWidget);
    expect(find.text('Compare final orders'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Stock Distribution shows target readiness and run outcome',
      (tester) async {
    final run = DistributionRun.fromJson({
      'run_id': 'run-1',
      'source_store_code': 'NMW',
      'status': 'completed',
      'stores_total': 2,
      'stores_succeeded': 1,
      'stores_failed': 1,
      'total_products': 100,
      'total_stock_qty': 250,
    });
    await tester.pumpWidget(_app(const StockDistributionScreen(), [
      stockDistributionDashboardProvider.overrideWith(
        (ref) async => StockDistributionDashboard(
          sourceStoreCode: 'NMW',
          targets: const [
            DistributionTarget(
              storeId: 'store-1',
              storeCode: 'NMS',
              storeName: 'Nathan Medicals',
              enabled: true,
              localSupplierCode: '94',
            ),
          ],
          runs: [run],
        ),
      ),
    ]));
    await tester.pumpAndSettle();

    expect(find.text('Nathan Medicals (NMS)'), findsOneWidget);
    expect(find.text('Ready'), findsOneWidget);
    expect(find.text('Generate all'), findsOneWidget);
    expect(find.text('1/2 stores · 100 products · 250 units'), findsOneWidget);
    expect(find.text('Retry failed'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Procurement conflicts only shows rejected procurement edits',
      (tester) async {
    final now = DateTime(2026, 8, 19);
    OutboxEntry entry(int id, String kind, String summary) => OutboxEntry(
          id: id,
          kind: kind,
          scope: 'scope-$id',
          payload: '{}',
          status: OutboxStatus.deadLetter.name,
          attemptCount: 8,
          summary: summary,
          createdAt: now,
          updatedAt: now,
        );
    await tester.pumpWidget(_app(const ProcurementConflictsScreen(), [
      outboxOutstandingProvider.overrideWith(
        (ref) => Stream.value([
          entry(1, PurchaseOutboxKinds.finalQty, 'Final quantity'),
          entry(2, 'document.item', 'Invoice line'),
        ]),
      ),
    ]));
    await tester.pump();

    expect(find.text('Final quantity'), findsOneWidget);
    expect(find.text('Resolve'), findsOneWidget);
    expect(find.text('Invoice line'), findsNothing);
  });
}
