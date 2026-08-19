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
