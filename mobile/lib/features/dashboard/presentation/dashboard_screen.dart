import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';

/// Phase 1 landing surface after login + store selection.
///
/// This is intentionally a thin shell — it only confirms the authenticated
/// session and active store. Business modules (inventory, procurement, CRM, HR,
/// education) are Phase 2+ and are deliberately NOT implemented here.
class DashboardScreen extends ConsumerWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final user = auth.user;
    final store = auth.selectedStore;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Nexora'),
        actions: [
          IconButton(
            tooltip: 'Change store',
            icon: const Icon(Icons.swap_horiz),
            onPressed: () =>
                ref.read(authControllerProvider.notifier).clearStore(),
          ),
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Welcome, ${user?.displayName ?? ''}',
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '@${user?.username ?? ''}',
                    style: Theme.of(context)
                        .textTheme
                        .bodyMedium
                        ?.copyWith(color: AppColors.slate),
                  ),
                  const Divider(height: 28),
                  _InfoRow(
                    icon: Icons.storefront_outlined,
                    label: 'Active store',
                    value: store?.storeName ?? '—',
                  ),
                  if (store?.storeCode != null)
                    _InfoRow(
                      icon: Icons.tag,
                      label: 'Store code',
                      value: store!.storeCode!,
                    ),
                  _InfoRow(
                    icon: Icons.badge_outlined,
                    label: 'Account type',
                    value:
                        (user?.isPlatformUser ?? false) ? 'Platform' : 'Store user',
                  ),
                  _InfoRow(
                    icon: Icons.grid_view_rounded,
                    label: 'Modules granted',
                    value: '${user?.modules.length ?? 0}',
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Icon(icon, size: 20, color: AppColors.slate),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              label,
              style: Theme.of(context)
                  .textTheme
                  .bodyMedium
                  ?.copyWith(color: AppColors.slate),
            ),
          ),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
