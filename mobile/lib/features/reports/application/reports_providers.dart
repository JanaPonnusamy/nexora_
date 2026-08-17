import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/reports/data/reports_api.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';

final reportsApiProvider = Provider<ReportsApi>(
  (ref) => ReportsApi(ref.watch(dioProvider)),
);

/// The report catalog. Cached for the session — it is static metadata that
/// only changes when the server is redeployed.
final reportCatalogProvider = FutureProvider<List<ReportDef>>(
  (ref) => ref.watch(reportsApiProvider).catalog(),
);

/// Catalog grouped by the server's own `group` field, in first-seen order so
/// the sections match the web console rather than sorting alphabetically.
final groupedReportCatalogProvider =
    FutureProvider<Map<String, List<ReportDef>>>((ref) async {
  final reports = await ref.watch(reportCatalogProvider.future);
  final grouped = <String, List<ReportDef>>{};
  for (final report in reports) {
    grouped.putIfAbsent(report.group, () => []).add(report);
  }
  return grouped;
});

/// The tenant and store every report call must be scoped to.
///
/// Reports are per-store by contract (`assert_store_access` on the server), so
/// a session without a selected store cannot run one at all.
class ReportScope {
  const ReportScope({required this.tenantId, required this.storeId});

  final String tenantId;
  final String storeId;
}

final reportScopeProvider = Provider<ReportScope?>((ref) {
  final auth = ref.watch(authControllerProvider);
  final store = auth.selectedStore;
  final tenantId = auth.user?.tenantId ?? store?.tenantId;
  if (store == null || tenantId == null || tenantId.isEmpty) return null;
  return ReportScope(tenantId: tenantId, storeId: store.storeId);
});

/// Supplier options for the reports that filter by supplier.
final reportSuppliersProvider =
    FutureProvider.autoDispose.family<List<SupplierOption>, String>(
  (ref, query) async {
    final scope = ref.watch(reportScopeProvider);
    if (scope == null) return const [];
    return ref.watch(reportsApiProvider).suppliers(
          tenantId: scope.tenantId,
          storeId: scope.storeId,
          query: query,
        );
  },
);
