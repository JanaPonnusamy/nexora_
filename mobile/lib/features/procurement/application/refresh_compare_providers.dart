import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/procurement/application/cycle_providers.dart';
import 'package:nexora_mobile/features/procurement/application/purchase_workspace_providers.dart';
import 'package:nexora_mobile/features/procurement/data/refresh_compare_api.dart';
import 'package:nexora_mobile/features/procurement/domain/cycle_models.dart';
import 'package:nexora_mobile/features/procurement/domain/refresh_compare_models.dart';

final refreshCompareApiProvider = Provider<RefreshCompareApi>(
  (ref) => RefreshCompareApi(
    ref.watch(dioProvider),
    ref.watch(purchaseWorkspaceApiProvider),
  ),
);

class RefreshCompareSetup {
  const RefreshCompareSetup({required this.cycles, required this.refreshes});

  final List<ProcurementCycle> cycles;
  final List<ProcurementRefresh> refreshes;
}

final refreshCompareSetupProvider =
    FutureProvider.autoDispose<RefreshCompareSetup>((ref) async {
  final scope = ref.watch(cycleScopeProvider);
  if (scope == null) {
    return const RefreshCompareSetup(cycles: [], refreshes: []);
  }
  final results = await Future.wait<Object>([
    ref.watch(cycleApiProvider).cycles(
          tenantId: scope.tenantId,
          storeId: scope.storeId,
          pageSize: 100,
        ),
    ref.watch(refreshCompareApiProvider).refreshes(
          tenantId: scope.tenantId,
          storeId: scope.storeId,
        ),
  ]);
  return RefreshCompareSetup(
    cycles: (results[0] as CyclePage).items,
    refreshes: results[1] as List<ProcurementRefresh>,
  );
});
