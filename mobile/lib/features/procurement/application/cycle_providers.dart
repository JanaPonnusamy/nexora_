import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/procurement/data/cycle_api.dart';
import 'package:nexora_mobile/features/procurement/domain/cycle_models.dart';

final cycleApiProvider = Provider<CycleApi>(
  (ref) => CycleApi(ref.watch(dioProvider)),
);

/// Tenant and store for the current session, or null before one is chosen.
class CycleScope {
  const CycleScope({required this.tenantId, required this.storeId});

  final String tenantId;
  final String storeId;
}

final cycleScopeProvider = Provider<CycleScope?>((ref) {
  final auth = ref.watch(authControllerProvider);
  final store = auth.selectedStore;
  final tenantId = auth.activeTenantId;
  if (store == null || tenantId == null) return null;
  return CycleScope(tenantId: tenantId, storeId: store.storeId);
});

/// Who a close is recorded against. The server writes this into the cycle's
/// audit fields, so a blank actor makes a close untraceable.
final cycleActorProvider = Provider<String?>(
  (ref) => ref.watch(authControllerProvider).user?.username,
);

/// Cycles for the active store, newest first as the server returns them.
///
/// `autoDispose` because the console is a screen you dip into: holding a page
/// of cycles after the user has moved on costs memory and guarantees the next
/// visit shows stale statuses.
final cyclesProvider =
    FutureProvider.autoDispose.family<CyclePage, String?>((ref, status) async {
  final scope = ref.watch(cycleScopeProvider);
  if (scope == null) {
    return const CyclePage(items: [], total: 0, page: 1, pageSize: 20);
  }
  return ref.watch(cycleApiProvider).cycles(
        tenantId: scope.tenantId,
        storeId: scope.storeId,
        status: status,
      );
});
