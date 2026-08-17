import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/error_view.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/store_selection/application/store_options_provider.dart';

/// Lets the signed-in user pick the store to operate within. Options come from
/// the user's role entitlements, or `/api/stores` for platform users. Choosing
/// a store advances the router to the dashboard.
class StoreSelectionScreen extends ConsumerWidget {
  const StoreSelectionScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final options = ref.watch(storeOptionsProvider);
    final user = ref.watch(authControllerProvider).user;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Select a store'),
        actions: [
          IconButton(
            tooltip: 'Sign out',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
            child: Text(
              'Hi ${user?.displayName ?? ''}, choose the store you want to work in.',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: AppColors.textMuted,
                  ),
            ),
          ),
          Expanded(
            child: options.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (err, _) => ErrorView(
                message: err.toString(),
                onRetry: () => ref.invalidate(storeOptionsProvider),
              ),
              data: (stores) {
                if (stores.isEmpty) {
                  return const ErrorView(
                    icon: Icons.store_mall_directory_outlined,
                    message:
                        'No stores are assigned to your account. Contact your administrator.',
                  );
                }
                return ListView.separated(
                  padding: const EdgeInsets.all(16),
                  itemCount: stores.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (_, i) => _StoreTile(store: stores[i]),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _StoreTile extends ConsumerWidget {
  const _StoreTile({required this.store});

  final SelectedStore store;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        leading: CircleAvatar(
          backgroundColor: AppColors.accent.withValues(alpha: 0.12),
          child: const Icon(Icons.storefront_outlined, color: AppColors.accent),
        ),
        title: Text(
          store.storeName,
          style: const TextStyle(fontWeight: FontWeight.w600),
        ),
        subtitle:
            store.storeCode != null ? Text('Code: ${store.storeCode}') : null,
        trailing: const Icon(Icons.chevron_right),
        onTap: () =>
            ref.read(authControllerProvider.notifier).selectStore(store),
      ),
    );
  }
}
