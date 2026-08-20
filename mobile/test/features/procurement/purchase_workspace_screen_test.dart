import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/procurement/application/purchase_workspace_providers.dart';
import 'package:nexora_mobile/features/procurement/domain/purchase_workspace_models.dart';
import 'package:nexora_mobile/features/procurement/presentation/purchase_workspace_screen.dart';

const _context = PurchaseWorkspaceContext(
  tenantId: 'tenant-1',
  storeId: 'store-1',
  refreshId: 'refresh-1',
);

const _item = PurchaseWorkspaceItem(
  orderItemId: 'item-1',
  productCode: '1042',
  productName: 'Paracetamol 500mg',
  suggestedQty: 10,
  finalQty: 12,
  assignedQty: 4,
  remainingQty: 8,
  status: 'partial',
  movementClass: 'FAST',
  unitDescription: '10 TAB',
);

Widget _harness(PurchaseWorkspaceData? data) => ProviderScope(
      overrides: [
        isOnlineProvider.overrideWith((ref) => true),
        purchaseWorkspaceProvider('').overrideWith((ref) async => data),
      ],
      child: MaterialApp(
        theme: AppTheme.dark,
        home: const PurchaseWorkspaceScreen(),
      ),
    );

void main() {
  testWidgets('renders the reduced field workspace as mobile product cards',
      (tester) async {
    await tester.pumpWidget(
      _harness(
        const PurchaseWorkspaceData(
          context: _context,
          page: PurchaseWorkspacePage(
            items: [_item],
            total: 1,
            page: 1,
            pageSize: 50,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Purchase Workspace'), findsOneWidget);
    expect(find.text('Paracetamol 500mg'), findsOneWidget);
    expect(find.text('Suggested 10'), findsOneWidget);
    expect(find.text('Final 12'), findsOneWidget);
    expect(find.text('Remaining 8'), findsOneWidget);
    expect(find.text('Quantity'), findsOneWidget);
    expect(find.text('Assign'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('explains that an active refresh is required', (tester) async {
    await tester.pumpWidget(_harness(null));
    await tester.pumpAndSettle();

    expect(
        find.text('Start a refresh in Cycle Console first.'), findsOneWidget);
  });

  testWidgets('quantity action opens the focused edit dialog', (tester) async {
    await tester.pumpWidget(
      _harness(
        const PurchaseWorkspaceData(
          context: _context,
          page: PurchaseWorkspacePage(
            items: [_item],
            total: 1,
            page: 1,
            pageSize: 50,
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Quantity'));
    await tester.pumpAndSettle();

    expect(find.text('Final quantity'), findsOneWidget);
    expect(find.text('Suggested: 10'), findsOneWidget);
    expect(find.text('Save'), findsOneWidget);
  });
}
