import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';

/// Phase 2 — what configuration is cached locally, its versions and freshness.
class ConfigurationStatusScreen extends ConsumerWidget {
  const ConfigurationStatusScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cached = ref.watch(cachedStoreConfigProvider);
    final entries = ref.watch(allConfigProvider);
    final agent = ref.read(agentManagerProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Configuration Status')),
      body: RefreshIndicator(
        onRefresh: () async {
          await agent.refreshConfiguration();
          ref.invalidate(allConfigProvider);
        },
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SectionCard(
              title: 'Store configuration',
              icon: Icons.storefront_outlined,
              trailing: cached.maybeWhen(
                data: (c) => c == null
                    ? const StatusPill(
                        label: 'Not cached', color: AppColors.slate,)
                    : StatusPill(
                        label: 'v${c.version}', color: AppColors.primary,),
                orElse: () => const SizedBox.shrink(),
              ),
              children: [
                cached.when(
                  loading: () => const Center(
                    child: Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2.2),
                      ),
                    ),
                  ),
                  error: (e, _) => Text('$e'),
                  data: (c) {
                    if (c == null) {
                      return const Text(
                        'No store configuration cached yet. Pull to refresh once online.',
                        style: TextStyle(color: AppColors.slate),
                      );
                    }
                    final s = c.store;
                    return Column(
                      children: [
                        InfoRow(label: 'Store name', value: s.storeName),
                        InfoRow(label: 'Store code', value: s.storeCode),
                        InfoRow(label: 'Store ID', value: s.storeId),
                        InfoRow(label: 'Tenant ID', value: s.tenantId),
                        InfoRow(
                          label: 'Active',
                          valueWidget: StatusPill(
                            label: s.isActive ? 'Active' : 'Inactive',
                            color: s.isActive
                                ? AppColors.success
                                : AppColors.slate,
                          ),
                        ),
                        InfoRow(
                            label: 'Downloaded',
                            value: formatRelative(c.fetchedAt),),
                      ],
                    );
                  },
                ),
              ],
            ),
            const SizedBox(height: 12),
            SectionCard(
              title: 'Cache entries',
              icon: Icons.folder_open_outlined,
              children: [
                entries.when(
                  loading: () => const SizedBox(
                    height: 40,
                    child: Center(
                      child: SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2.2),
                      ),
                    ),
                  ),
                  error: (e, _) => Text('$e'),
                  data: (rows) => rows.isEmpty
                      ? const Text('Nothing cached yet.',
                          style: TextStyle(color: AppColors.slate),)
                      : Column(
                          children: [
                            for (final r in rows)
                              InfoRow(
                                label: r.key,
                                valueWidget: Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Text('v${r.version}',
                                        style: const TextStyle(
                                            fontWeight: FontWeight.w600,),),
                                    Text(
                                      formatRelative(r.updatedAt),
                                      style: const TextStyle(
                                          fontSize: 12, color: AppColors.slate,),
                                    ),
                                  ],
                                ),
                              ),
                          ],
                        ),
                ),
              ],
            ),
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}
