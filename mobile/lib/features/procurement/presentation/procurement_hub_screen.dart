import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/router/app_routes.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';

/// Root of the Procure tab: a launcher for the procurement modules.
///
/// Shipped as a hub from the start so the tab has a stable shape — each module
/// swaps its `enabled: false` for a real destination as its phase lands,
/// without the surrounding navigation changing.
class ProcurementHubScreen extends ConsumerWidget {
  const ProcurementHubScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authControllerProvider).user;
    final canUseLegacy = user == null ||
        user.isPlatformUser ||
        user.roles.any((role) {
          final name =
              role.roleName.toLowerCase().replaceAll(RegExp(r'[_-]'), ' ');
          return name.contains('superadmin') || name.contains('super admin');
        });

    return Scaffold(
      appBar: AppBar(title: const Text('Procurement')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          const SectionHeader(title: 'DAILY', icon: Icons.today_outlined),
          const _ModuleTile(
            title: 'Purchase Workspace',
            subtitle: 'Review products, set quantities, assign suppliers',
            icon: Icons.shopping_cart_outlined,
            phase: 'Phase 5',
          ),
          const _ModuleTile(
            title: 'Suppliers',
            subtitle: 'Supplier master, stock and ranking',
            icon: Icons.local_shipping_outlined,
            phase: 'Phase 3',
          ),
          const SizedBox(height: 12),
          const SectionHeader(title: 'CYCLES', icon: Icons.autorenew_rounded),
          const _LiveTile(
            title: 'Cycle & Refresh Console',
            subtitle: 'Open cycles, start and close refreshes',
            icon: Icons.playlist_play_rounded,
            route: AppRoutes.cycleConsoleFullPath,
          ),
          const _ModuleTile(
            title: 'Refresh Compare',
            subtitle: 'Diff the final order between two refreshes',
            icon: Icons.compare_arrows_rounded,
            phase: 'Phase 5',
          ),
          const SizedBox(height: 12),
          const SectionHeader(title: 'DISTRIBUTION', icon: Icons.hub_outlined),
          const _ModuleTile(
            title: 'Stock Distribution',
            subtitle: 'Push warehouse stock out to stores',
            icon: Icons.warehouse_outlined,
            phase: 'Phase 5',
          ),
          if (canUseLegacy)
            const _LiveTile(
              title: 'Legacy Order Console',
              subtitle: 'Store health, jobs and quantity review',
              icon: Icons.history_rounded,
              route: AppRoutes.legacyOrderConsoleFullPath,
            ),
        ],
      ),
    );
  }
}

/// A module entry that is visible but not yet navigable. The phase badge is the
/// point — it tells the user this is scheduled, not broken.
class _ModuleTile extends StatelessWidget {
  const _ModuleTile({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.phase,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final String phase;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: 0.55,
      child: ActionTile(
        title: title,
        subtitle: subtitle,
        icon: icon,
        color: AppColors.textMuted,
        trailing: InfoChip(label: phase, color: AppColors.warning),
      ),
    );
  }
}

/// A module that is actually built. Full opacity and a real tap target, so the
/// difference between "shipped" and "planned" is visible at a glance rather
/// than only on tapping.
class _LiveTile extends StatelessWidget {
  const _LiveTile({
    required this.title,
    required this.subtitle,
    required this.icon,
    required this.route,
  });

  final String title;
  final String subtitle;
  final IconData icon;
  final String route;

  @override
  Widget build(BuildContext context) {
    return ActionTile(
      title: title,
      subtitle: subtitle,
      icon: icon,
      color: AppColors.accent,
      onTap: () => context.go(route),
    );
  }
}
