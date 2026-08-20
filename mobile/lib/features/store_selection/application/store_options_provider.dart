import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';

/// Produces the list of stores the current user may select.
///
/// - A **store-scoped user** sees the distinct stores granted by their roles.
/// - A **platform user** always loads the full active store list from
///   `GET /api/stores` (optionally narrowed to their tenant), even if they also
///   carry one or more store-scoped roles.
final storeOptionsProvider = FutureProvider.autoDispose<List<SelectedStore>>(
  (ref) async {
    final auth = ref.watch(authControllerProvider);
    final user = auth.user;
    if (user == null) return const [];

    // Platform users must always see the complete store list. They can still
    // carry store-scoped roles (for example after being assigned a temporary
    // operational role), so the presence of a role is not a safe way to
    // decide that their picker should be restricted.
    if (user.isPlatformUser) {
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
    }

    // Store-scoped users are restricted to entitlements from the login
    // payload.
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

    // A non-platform user with no store role has no selectable stores.
    // Returning an empty list keeps the authorization boundary intact instead
    // of accidentally exposing every store through the platform endpoint.
    return const [];
  },
);
