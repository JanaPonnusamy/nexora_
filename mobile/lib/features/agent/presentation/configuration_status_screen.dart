import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
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
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
          children: [
            const SectionHeader(
              title: 'STORE CONFIGURATION',
              icon: Icons.storefront_outlined,
            ),
            cached.when(
              loading: () => const StatusCard(
                accentColor: AppColors.rule,
                child: InlineLoading(),
              ),
              error: (e, _) => StatusCard(
                accentColor: AppColors.danger,
                child:
                    Text('$e', style: const TextStyle(color: AppColors.danger)),
              ),
              data: (c) {
                if (c == null) {
                  return const StatusCard(
                    accentColor: AppColors.textMuted,
                    child: EmptyState(
                      message:
                          'No store configuration cached yet. Pull to refresh once online.',
                      icon: Icons.cloud_off_rounded,
                    ),
                  );
                }
                final s = c.store;
                return StatusCard(
                  accentColor:
                      s.isActive ? AppColors.success : AppColors.textMuted,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              s.storeName,
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                          StatusBadge(
                            label: 'v${c.version}',
                            color: AppColors.accent,
                            dense: true,
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          InfoChip(
                            label: s.storeCode,
                            icon: Icons.storefront_outlined,
                          ),
                          InfoChip(
                            label: s.isActive ? 'Active' : 'Inactive',
                            icon: s.isActive
                                ? Icons.check_circle_outline
                                : Icons.remove_circle_outline,
                            color: s.isActive
                                ? AppColors.success
                                : AppColors.textMuted,
                          ),
                        ],
                      ),
                      const Divider(height: 24),
                      InfoRow(label: 'Store ID', value: s.storeId),
                      InfoRow(label: 'Tenant ID', value: s.tenantId),
                      InfoRow(
                        label: 'Downloaded',
                        value: formatRelative(c.fetchedAt),
                      ),
                    ],
                  ),
                );
              },
            ),
            const SizedBox(height: 16),
            SectionHeader(
              title: 'CACHE ENTRIES',
              icon: Icons.folder_open_outlined,
              trailing: entries.maybeWhen(
                data: (rows) => Text(
                  '${rows.length}',
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textMuted,
                  ),
                ),
                orElse: () => null,
              ),
            ),
            StatusCard(
              accentColor: AppColors.rule,
              child: entries.when(
                loading: () => const InlineLoading(),
                error: (e, _) => Text('$e'),
                data: (rows) => rows.isEmpty
                    ? const EmptyState(
                        message: 'Nothing cached yet.',
                        icon: Icons.folder_off_outlined,
                      )
                    : Column(
                        children: [
                          for (final r in rows)
                            InfoRow(
                              label: r.key,
                              valueWidget: Column(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Text(
                                    'v${r.version}',
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  Text(
                                    formatRelative(r.updatedAt),
                                    style: const TextStyle(
                                      fontSize: 12,
                                      color: AppColors.textMuted,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                        ],
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
