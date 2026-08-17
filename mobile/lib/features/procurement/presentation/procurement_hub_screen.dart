import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';

/// Root of the Procure tab: a launcher for the procurement modules.
///
/// Shipped as a hub from the start so the tab has a stable shape — each module
/// swaps its `enabled: false` for a real destination as its phase lands,
/// without the surrounding navigation changing.
class ProcurementHubScreen extends StatelessWidget {
  const ProcurementHubScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Procurement')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: const [
          SectionHeader(title: 'DAILY', icon: Icons.today_outlined),
          _ModuleTile(
            title: 'Purchase Workspace',
            subtitle: 'Review products, set quantities, assign suppliers',
            icon: Icons.shopping_cart_outlined,
            phase: 'Phase 5',
          ),
          _ModuleTile(
            title: 'Suppliers',
            subtitle: 'Supplier master, stock and ranking',
            icon: Icons.local_shipping_outlined,
            phase: 'Phase 3',
          ),
          SizedBox(height: 12),
          SectionHeader(title: 'CYCLES', icon: Icons.autorenew_rounded),
          _ModuleTile(
            title: 'Cycle & Refresh Console',
            subtitle: 'Run and monitor the sync → cycle → refresh pipeline',
            icon: Icons.playlist_play_rounded,
            phase: 'Phase 4',
          ),
          _ModuleTile(
            title: 'Refresh Compare',
            subtitle: 'Diff the final order between two refreshes',
            icon: Icons.compare_arrows_rounded,
            phase: 'Phase 5',
          ),
          SizedBox(height: 12),
          SectionHeader(title: 'DISTRIBUTION', icon: Icons.hub_outlined),
          _ModuleTile(
            title: 'Stock Distribution',
            subtitle: 'Push warehouse stock out to stores',
            icon: Icons.warehouse_outlined,
            phase: 'Phase 5',
          ),
          _ModuleTile(
            title: 'Legacy Order Console',
            subtitle: 'Drive the legacy ordering system',
            icon: Icons.history_rounded,
            phase: 'Phase 4',
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
