import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/procurement/data/legacy_order_api.dart';
import 'package:nexora_mobile/features/procurement/domain/legacy_order_models.dart';

final legacyOrderApiProvider = Provider<LegacyOrderApi>(
  (ref) => LegacyOrderApi(ref.watch(dioProvider)),
);

final legacyHealthProvider = FutureProvider.autoDispose<LegacyDbHealth>(
  (ref) => ref.watch(legacyOrderApiProvider).health(),
);

/// Store operations are separate from DB health: `/db/health` can explain an
/// OrderNMC outage even when `/stores` is returning 503.
final legacyConsoleProvider = FutureProvider.autoDispose<LegacyConsoleData>(
  (ref) async {
    final api = ref.watch(legacyOrderApiProvider);
    final results = await Future.wait([
      api.stores(),
      api.jobs(),
      api.defaults(),
    ]);
    return LegacyConsoleData(
      stores: results[0] as List<LegacyStore>,
      jobs: results[1] as List<LegacyJob>,
      defaults: results[2] as LegacyDefaults,
    );
  },
);

final previousOrdersProvider = FutureProvider.autoDispose
    .family<List<PreviousOrder>, String>((ref, storeName) {
  if (storeName.isEmpty) return const [];
  return ref.watch(legacyOrderApiProvider).previousOrders(storeName);
});

class PreviousOrderRequest {
  const PreviousOrderRequest({required this.storeName, required this.orderId});

  final String storeName;
  final int orderId;

  @override
  bool operator ==(Object other) =>
      other is PreviousOrderRequest &&
      storeName == other.storeName &&
      orderId == other.orderId;

  @override
  int get hashCode => Object.hash(storeName, orderId);
}

final previousOrderSuppliersProvider = FutureProvider.autoDispose
    .family<List<PreviousOrderSupplier>, PreviousOrderRequest>((ref, request) {
  return ref.watch(legacyOrderApiProvider).previousOrderSuppliers(
        storeName: request.storeName,
        orderId: request.orderId,
      );
});

class SupplierComparisonRequest extends PreviousOrderRequest {
  const SupplierComparisonRequest({
    required super.storeName,
    required super.orderId,
    required this.supplierCode,
  });

  final String supplierCode;

  @override
  bool operator ==(Object other) =>
      other is SupplierComparisonRequest &&
      storeName == other.storeName &&
      orderId == other.orderId &&
      supplierCode == other.supplierCode;

  @override
  int get hashCode => Object.hash(storeName, orderId, supplierCode);
}

final supplierComparisonProductsProvider = FutureProvider.autoDispose
    .family<List<SupplierComparisonProduct>, SupplierComparisonRequest>(
        (ref, request) {
  return ref.watch(legacyOrderApiProvider).previousOrderSupplierProducts(
        storeName: request.storeName,
        orderId: request.orderId,
        supplierCode: request.supplierCode,
      );
});

final qtyCheckRowsProvider = FutureProvider.autoDispose
    .family<List<QtyCheckRow>, String>((ref, storeName) {
  if (storeName.isEmpty) return const [];
  return ref.watch(legacyOrderApiProvider).qtyCheckRows(storeName);
});

class QtyCheckRequest {
  const QtyCheckRequest({
    required this.storeName,
    required this.productCode,
    required this.mode,
  });

  final String storeName;
  final int productCode;
  final String mode;

  @override
  bool operator ==(Object other) =>
      other is QtyCheckRequest &&
      storeName == other.storeName &&
      productCode == other.productCode &&
      mode == other.mode;

  @override
  int get hashCode => Object.hash(storeName, productCode, mode);
}

final qtyCheckDetailsProvider = FutureProvider.autoDispose
    .family<QtyCheckDetails, QtyCheckRequest>((ref, request) {
  return ref.watch(legacyOrderApiProvider).qtyCheckDetails(
        storeName: request.storeName,
        productCode: request.productCode,
        mode: request.mode,
      );
});
