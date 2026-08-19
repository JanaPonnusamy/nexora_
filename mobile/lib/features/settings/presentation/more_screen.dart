import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';

/// Root of the More tab: account, store, system diagnostics and session
/// actions — everything that does not warrant a tab of its own.
class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final user = auth.user;
    final store = auth.selectedStore;

    return Scaffold(
      appBar: AppBar(title: const Text('More')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
        children: [
          _AccountCard(
            name: user?.displayName ?? '—',
            username: user?.username ?? '',
            isPlatformUser: user?.isPlatformUser ?? false,
          ),
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'ACTIVE STORE',
            icon: Icons.storefront_outlined,
          ),
          ActionTile(
            title: store?.storeName ?? 'No store selected',
            subtitle: store?.storeCode ?? 'Tap to choose a store',
            icon: Icons.storefront_rounded,
            trailing: const Icon(
              Icons.swap_horiz_rounded,
              size: 19,
              color: AppColors.textMuted,
            ),
            onTap: () => ref.read(authControllerProvider.notifier).clearStore(),
          ),
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'WORKSPACE',
            icon: Icons.workspaces_outline,
          ),
          ActionTile(
            title: 'Reports',
            subtitle: 'Sales, margin and stock reports for this store',
            icon: Icons.insert_chart_outlined,
            color: AppColors.info,
            onTap: () => context.go(AppRoutes.reportsFullPath),
          ),
          ActionTile(
            title: 'Suppliers',
            subtitle: 'Supplier master, searchable offline',
            icon: Icons.local_shipping_outlined,
            color: AppColors.success,
            onTap: () => context.go(AppRoutes.suppliersFullPath),
          ),
          ActionTile(
            title: 'Time Report',
            subtitle: 'Attendance: daily, miss punch, per user, inactive',
            icon: Icons.schedule_outlined,
            color: AppColors.accentInk,
            onTap: () => context.go(AppRoutes.timeReportFullPath),
          ),
          // Platform-ops only: the endpoint 403s everyone else, so offering
          // the tile to a store user would be a guaranteed dead end.
          if (user?.isPlatformUser ?? false)
            ActionTile(
              title: 'Pass Gen',
              subtitle: 'Store passcodes for the field ordering app',
              icon: Icons.password_rounded,
              color: AppColors.warning,
              onTap: () => context.go(AppRoutes.passGenFullPath),
            ),
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'SYSTEM',
            icon: Icons.settings_outlined,
          ),
          // One entry rather than four. Device Status, Configuration Status and
          // Agent Settings moved into Settings alongside security, server,
          // storage and pending changes — this list had grown long enough that
          // Sign out fell below the fold, and the fix for that is grouping.
          ActionTile(
            title: 'Settings',
            subtitle: 'Security, server, storage, pending changes and '
                'diagnostics',
            icon: Icons.settings_rounded,
            onTap: () => context.go(AppRoutes.settingsFullPath),
          ),
          const SizedBox(height: 20),
          const SectionHeader(
            title: 'SESSION',
            icon: Icons.lock_outline_rounded,
          ),
          ActionTile(
            title: 'Sign out',
            subtitle: 'Clears the session on this device',
            icon: Icons.logout_rounded,
            color: AppColors.danger,
            onTap: () => _confirmSignOut(context, ref),
          ),
        ],
      ),
    );
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text(
          'Anything still queued for upload stays on this device and resumes '
          'when you sign back in.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            style: TextButton.styleFrom(foregroundColor: AppColors.dangerInk),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );

    if (confirmed ?? false) {
      await ref.read(authControllerProvider.notifier).logout();
    }
  }
}

class _AccountCard extends StatelessWidget {
  const _AccountCard({
    required this.name,
    required this.username,
    required this.isPlatformUser,
  });

  final String name;
  final String username;
  final bool isPlatformUser;

  @override
  Widget build(BuildContext context) {
    final initial = name.isNotEmpty ? name[0].toUpperCase() : '?';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: AppColors.brandBlue,
                ),
                shape: BoxShape.circle,
              ),
              alignment: Alignment.center,
              child: Text(
                initial,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.w800,
                  color: AppColors.textOn,
                ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: const TextStyle(
                      fontSize: 17,
                      fontWeight: FontWeight.w700,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 2),
                  Text(
                    '@$username',
                    style: const TextStyle(
                      fontSize: 13,
                      color: AppColors.textMuted,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            InfoChip(
              label: isPlatformUser ? 'Platform' : 'Store',
              icon: isPlatformUser
                  ? Icons.shield_outlined
                  : Icons.storefront_outlined,
              color: isPlatformUser ? AppColors.accent : AppColors.textMuted,
            ),
          ],
        ),
      ),
    );
  }
}
