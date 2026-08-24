import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/auth/data/models/user_role.dart';
import 'package:nexora_mobile/features/procurement/application/legacy_order_providers.dart';
import 'package:nexora_mobile/features/procurement/data/legacy_order_api.dart';
import 'package:nexora_mobile/features/procurement/domain/legacy_order_models.dart';
import 'package:nexora_mobile/features/procurement/presentation/legacy_order_console_screen.dart';
import 'package:nexora_mobile/features/procurement/presentation/procurement_hub_screen.dart';

const _store = LegacyStore(
  code: '7',
  name: 'Nathan Medicals',
  server: '10.0.0.7',
  database: 'NMS',
  isActive: true,
  lastSyncStatus: 'SUCCESS',
);

const _health = LegacyDbHealth(
  database: 'OrderNMC',
  server: 'localhost',
  reachable: true,
  online: true,
  state: 'ONLINE',
  access: 'MULTI_USER',
  message: 'Database is ONLINE and MULTI_USER.',
);

const _job = LegacyJob(
  id: 'job-1',
  kind: LegacyJobKind.sync,
  rawKind: 'sync',
  storeName: 'Nathan Medicals',
  status: LegacyJobStatus.completed,
  rawStatus: 'completed',
  step: 4,
  totalSteps: 4,
  message: 'Sync completed.',
  log: [],
);

const _row = QtyCheckRow(
  productCode: 91,
  productName: 'Paracetamol 500mg',
  orderQty: 12,
  totalStock: 4,
  saleUnit: 10,
  salesQty: 28,
  mrp: 25.5,
  maxSaleQty: 8,
  unitDescription: '10 TABLETS',
);

const _details = QtyCheckDetails(
  purchases: [PurchaseDetail(receivedStock: 10, supplierName: 'NMW')],
  sales: [SalesDetail(quantity: 2, customer: 'Cash sale')],
  monthly: [MonthlyStat(month: '2026-08', sales: 20, stock: 4, purchases: 12)],
  history: [OrderHistoryEntry(orderQty: 8, remarks: 'Previous order')],
);

final _previousOrder = PreviousOrder(
  storeName: 'Nathan Medicals',
  orderId: 314,
  wantedAt: DateTime(2026, 8, 23, 14, 30),
);

const _previousSupplier = PreviousOrderSupplier(
  code: 'SUP-7',
  name: 'NMW Supplier',
  productCount: 1,
);

const _comparisonProduct = SupplierComparisonProduct(
  previousProductCode: 91,
  previousProductName: 'Paracetamol 500mg',
  currentProductCode: 91,
  currentProductName: 'Paracetamol 500mg',
  previousOrderedQty: 8,
  currentOrderQty: 12,
  previousStock: 6,
  currentStock: 4,
);

class _RecordingLegacyOrderApi extends LegacyOrderApi {
  _RecordingLegacyOrderApi() : super(Dio());

  int? comparedOrderId;
  String? comparedSupplierCode;

  @override
  Future<PreviousOrderComparison> comparePreviousOrder({
    required String storeName,
    required int orderId,
  }) async {
    comparedOrderId = orderId;
    return PreviousOrderComparison(
      storeName: storeName,
      orderId: orderId,
      affectedRows: 7,
    );
  }

  @override
  Future<PreviousOrderComparison> comparePreviousOrderSupplier({
    required String storeName,
    required int orderId,
    required String supplierCode,
  }) async {
    comparedSupplierCode = supplierCode;
    return PreviousOrderComparison(
      storeName: storeName,
      orderId: orderId,
      affectedRows: 3,
      supplierCode: supplierCode,
    );
  }
}

class _PlatformAuth extends AuthController {
  @override
  AuthState build() => const AuthState(
        status: AuthStatus.authenticated,
        user: AppUser(
          userId: 'platform',
          username: 'superadmin',
          isPlatformUser: true,
        ),
      );
}

class _StoreAuth extends AuthController {
  @override
  AuthState build() => const AuthState(
        status: AuthStatus.authenticated,
        user: AppUser(
          userId: 'store-user',
          username: 'buyer',
          roles: [
            UserRole(roleId: 'r-1', roleName: 'PURCHASE_MANAGER'),
          ],
        ),
      );
}

Widget _harness({_RecordingLegacyOrderApi? api}) {
  const request = QtyCheckRequest(
    storeName: 'Nathan Medicals',
    productCode: 91,
    mode: 'local',
  );
  return ProviderScope(
    overrides: [
      if (api != null) legacyOrderApiProvider.overrideWithValue(api),
      networkStatusProvider
          .overrideWith((ref) => Stream.value(NetworkStatus.online)),
      legacyConsoleProvider.overrideWith(
        (ref) async => const LegacyConsoleData(
          stores: [_store],
          jobs: [_job],
          defaults: LegacyDefaults(minDays: 13, maxDays: 18),
        ),
      ),
      legacyHealthProvider.overrideWith((ref) async => _health),
      qtyCheckRowsProvider('Nathan Medicals')
          .overrideWith((ref) async => const [_row]),
      qtyCheckDetailsProvider(request).overrideWith((ref) async => _details),
      previousOrdersProvider('Nathan Medicals')
          .overrideWith((ref) async => [_previousOrder]),
      previousOrderSuppliersProvider(
        const PreviousOrderRequest(
          storeName: 'Nathan Medicals',
          orderId: 314,
        ),
      ).overrideWith((ref) async => const [_previousSupplier]),
      supplierComparisonProductsProvider(
        const SupplierComparisonRequest(
          storeName: 'Nathan Medicals',
          orderId: 314,
          supplierCode: 'SUP-7',
        ),
      ).overrideWith((ref) async => const [_comparisonProduct]),
    ],
    child: MaterialApp(
      theme: AppTheme.dark,
      home: const LegacyOrderConsoleScreen(),
    ),
  );
}

Widget _outageHarness() => ProviderScope(
      overrides: [
        networkStatusProvider
            .overrideWith((ref) => Stream.value(NetworkStatus.online)),
        legacyConsoleProvider.overrideWith(
          (ref) => throw const ApiException(
            message: 'OrderNMC is unavailable.',
            statusCode: 503,
          ),
        ),
        legacyHealthProvider.overrideWith(
          (ref) async => const LegacyDbHealth(
            database: 'OrderNMC',
            server: 'localhost',
            reachable: true,
            online: false,
            state: 'RECOVERY_PENDING',
            access: 'MULTI_USER',
            message: 'Database is RECOVERY_PENDING / MULTI_USER.',
          ),
        ),
      ],
      child: MaterialApp(
        theme: AppTheme.dark,
        home: const LegacyOrderConsoleScreen(),
      ),
    );

void _tallPhone(WidgetTester tester) {
  tester.view.physicalSize = const Size(390, 1600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
}

void main() {
  testWidgets('hub shows Legacy Order only to an unrestricted login',
      (tester) async {
    _tallPhone(tester);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(_PlatformAuth.new),
        ],
        child: MaterialApp(
          theme: AppTheme.dark,
          home: const ProcurementHubScreen(),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('Legacy Order Console'), findsOneWidget);

    final suppliersTile = tester.widget<ActionTile>(
      find.ancestor(
        of: find.text('Suppliers'),
        matching: find.byType(ActionTile),
      ),
    );
    expect(suppliersTile.onTap, isNotNull);
    expect(find.text('Phase 3'), findsNothing);

    // Dispose the first ProviderContainer. Provider overrides are fixed for a
    // container's lifetime, so replacing one ProviderScope in-place would
    // deliberately preserve the platform-user override.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(_StoreAuth.new),
        ],
        child: MaterialApp(
          theme: AppTheme.dark,
          home: const ProcurementHubScreen(),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('Legacy Order Console'), findsNothing);
  });

  testWidgets('operations render health, store actions and recent jobs',
      (tester) async {
    _tallPhone(tester);
    await tester.pumpWidget(_harness());
    await tester.pumpAndSettle();

    expect(find.text('Database is ONLINE and MULTI_USER.'), findsOneWidget);
    expect(find.text('Nathan Medicals'), findsWidgets);
    expect(find.text('Sync'), findsOneWidget);
    expect(find.text('Order process'), findsOneWidget);
    expect(find.text('Stock update'), findsOneWidget);
    expect(find.text('Sync completed.'), findsOneWidget);
    expect(
      tester.takeException(),
      isNull,
      reason: 'buttons in a Wrap need finite minimum widths (§3.8)',
    );
  });

  testWidgets('database health still explains a stores endpoint outage',
      (tester) async {
    await tester.pumpWidget(_outageHarness());
    await tester.pumpAndSettle();

    expect(
      find.text('Database is RECOVERY_PENDING / MULTI_USER.'),
      findsOneWidget,
    );
    expect(find.text('Store operations unavailable'), findsOneWidget);
    expect(find.text('OrderNMC is unavailable.'), findsOneWidget);
  });

  testWidgets('qty check is a phone card rather than the desktop grid',
      (tester) async {
    await tester.pumpWidget(_harness());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Qty check'));
    await tester.pumpAndSettle();

    expect(find.text('Paracetamol 500mg'), findsOneWidget);
    expect(find.text('Suggested'), findsOneWidget);
    expect(find.text('Evidence'), findsOneWidget);
    expect(find.text('Review qty'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('evidence sheet exposes all four backend drill-downs',
      (tester) async {
    _tallPhone(tester);
    await tester.pumpWidget(_harness());
    await tester.pumpAndSettle();
    await tester.tap(find.text('Qty check'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Evidence'));
    await tester.pumpAndSettle();

    expect(find.text('Monthly statistics'), findsOneWidget);
    expect(find.text('Purchase / GRN history'), findsOneWidget);
    expect(find.text('Sales history'), findsOneWidget);
    expect(find.text('Previous orders'), findsOneWidget);
  });

  testWidgets('compare tab lists previous orders and confirms a full compare',
      (tester) async {
    _tallPhone(tester);
    await tester.pumpWidget(_harness());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Compare'));
    await tester.pumpAndSettle();

    expect(find.text('COMPARE PREVIOUS ORDER'), findsOneWidget);
    expect(find.text('Order #314'), findsOneWidget);
    expect(find.text('NMW Supplier'), findsOneWidget);
    expect(find.text('SUP-7 · 1 products'), findsOneWidget);

    await tester.tap(find.text('Compare entire order #314'));
    await tester.pumpAndSettle();

    expect(find.text('Compare order #314?'), findsOneWidget);
    expect(find.text('Compare order'), findsOneWidget);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
  });

  testWidgets('supplier review shows previous and current product values',
      (tester) async {
    _tallPhone(tester);
    await tester.pumpWidget(_harness());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Compare'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('NMW Supplier'));
    await tester.pumpAndSettle();

    expect(find.text('Paracetamol 500mg'), findsOneWidget);
    expect(find.text('Previous qty'), findsOneWidget);
    expect(find.text('Current qty'), findsOneWidget);
    expect(find.text('Previous stock'), findsOneWidget);
    expect(find.text('Current stock'), findsOneWidget);
    expect(find.text('Changed'), findsOneWidget);
    expect(find.text('Compare 1 products'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('confirmed comparisons call the full-order backend action',
      (tester) async {
    final api = _RecordingLegacyOrderApi();
    _tallPhone(tester);
    await tester.pumpWidget(_harness(api: api));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Compare'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Compare entire order #314'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Compare order'));
    await tester.pumpAndSettle();

    expect(api.comparedOrderId, 314);
    expect(
      find.text('Compared order #314. 7 row updates applied.'),
      findsOneWidget,
    );
  });

  testWidgets('confirmed supplier comparison calls the scoped backend action',
      (tester) async {
    final api = _RecordingLegacyOrderApi();
    _tallPhone(tester);
    await tester.pumpWidget(_harness(api: api));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Compare'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('NMW Supplier'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Compare 1 products'));
    await tester.pump();
    await tester.tap(find.text('Compare supplier'));
    await tester.pumpAndSettle();

    expect(api.comparedSupplierCode, 'SUP-7');
    expect(find.text('Compared NMW Supplier. 3 row updates applied.'),
        findsOneWidget);
  });
}
