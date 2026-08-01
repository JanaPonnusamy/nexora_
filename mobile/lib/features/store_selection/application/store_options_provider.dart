import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';

/// Produces the list of stores the current user may select.
///
/// - A **store-scoped user** carries their entitled stores in their roles (from
///   the login payload) — no extra request needed.
/// - A **platform user** has no store roles, so we fall back to `GET /api/stores`
///   (optionally narrowed to their tenant).
final storeOptionsProvider = FutureProvider.autoDispose<List<SelectedStore>>(
  (ref) async {
    final auth = ref.watch(authControllerProvider);
    final user = auth.user;
    if (user == null) return const [];

    // Prefer entitlements from the login payload.
    final roleStores = user.storeRoles;
    if (roleStores.isNotEmpty) {
      final seen = <String>{};
      final options = <SelectedStore>[];
      for (final r in roleStores) {
        final id = r.storeId!;
        if (seen.add(id)) {
          options.add(
            SelectedStore(
              storeId: id,
              storeName: r.storeName ?? r.storeCode ?? id,
              storeCode: r.storeCode,
              tenantId: user.tenantId,
            ),
          );
        }
      }
      options.sort((a, b) => a.storeName.compareTo(b.storeName));
      return options;
    }

    // Platform user: pull the full/tenant store list from the backend.
    final repo = ref.watch(storeRepositoryProvider);
    final stores = user.tenantId != null && user.tenantId!.isNotEmpty
        ? await repo.getByTenant(user.tenantId!)
        : await repo.getAll();

    final options = stores
        .where((s) => s.isActive)
        .map(SelectedStore.fromStore)
        .toList()
      ..sort((a, b) => a.storeName.compareTo(b.storeName));
    return options;
  },
);
