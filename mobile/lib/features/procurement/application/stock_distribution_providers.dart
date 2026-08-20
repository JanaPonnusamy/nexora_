import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/procurement/application/cycle_providers.dart';
import 'package:nexora_mobile/features/procurement/data/stock_distribution_api.dart';
import 'package:nexora_mobile/features/procurement/domain/stock_distribution_models.dart';

final stockDistributionApiProvider = Provider<StockDistributionApi>(
  (ref) => StockDistributionApi(ref.watch(dioProvider)),
);

class StockDistributionDashboard {
  const StockDistributionDashboard({
    required this.targets,
    required this.runs,
    required this.sourceStoreCode,
  });

  final List<DistributionTarget> targets;
  final List<DistributionRun> runs;
  final String sourceStoreCode;
}

final stockDistributionDashboardProvider =
    FutureProvider.autoDispose<StockDistributionDashboard>((ref) async {
  final scope = ref.watch(cycleScopeProvider);
  if (scope == null) {
    return const StockDistributionDashboard(
      targets: [],
      runs: [],
      sourceStoreCode: 'NMW',
    );
  }
  const source = 'NMW';
  final api = ref.watch(stockDistributionApiProvider);
  final result = await Future.wait<Object>([
    api.config(tenantId: scope.tenantId, sourceStoreCode: source),
    api.runs(tenantId: scope.tenantId),
  ]);
  return StockDistributionDashboard(
    targets: (result[0] as List<DistributionTarget>)
        .where((target) => target.storeCode != source)
        .toList(growable: false),
    runs: result[1] as List<DistributionRun>,
    sourceStoreCode: source,
  );
});
