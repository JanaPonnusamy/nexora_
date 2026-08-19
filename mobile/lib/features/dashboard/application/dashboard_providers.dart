import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/dashboard/data/dashboard_service.dart';
import 'package:nexora_mobile/features/dashboard/data/dashboard_summary.dart';

final dashboardServiceProvider = Provider<DashboardService>(
  (ref) => DashboardService(ref.watch(dioProvider)),
);

/// Home tab aggregate for the active store.
///
/// Keyed on the selected store so switching stores refetches rather than
/// showing the previous store's numbers.
final dashboardSummaryProvider = FutureProvider.autoDispose<DashboardSummary>((
  ref,
) async {
  final storeId = ref.watch(
    authControllerProvider.select((s) => s.selectedStore?.storeId),
  );
  return ref.watch(dashboardServiceProvider).fetch(storeId: storeId);
});
