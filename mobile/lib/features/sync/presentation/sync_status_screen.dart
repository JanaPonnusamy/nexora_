import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/sync/sync_status.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';
import 'package:nexora_mobile/features/sync/data/sync_control_center.dart';
import 'package:nexora_mobile/features/sync/presentation/widgets/sync_progress_card.dart';

/// Live view of the sync engine, built as a mobile hub: one hero status card,
/// a network strip for platform users, and drill-in bottom sheets for the
/// entity/queue/activity detail that used to live in dense inline tables.
class SyncStatusScreen extends ConsumerWidget {
  const SyncStatusScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final syncAsync = ref.watch(syncStateProvider);
    final agent = ref.watch(agentManagerProvider);
    final isPlatformUser = ref.watch(isPlatformUserProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Sync')),
      body: syncAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Sync unavailable: $e')),
        data: (state) => RefreshIndicator(
          onRefresh: () async {
            final futures = <Future<void>>[agent.triggerSync()];
            if (isPlatformUser) {
              ref.invalidate(syncControlCenterProvider);
              futures.add(ref.read(syncControlCenterProvider.future));
            }
            await Future.wait(futures);
          },
          child: ListView(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 96),
            children: [
              SyncProgressCard(state: state),
              if (isPlatformUser) ...[
                const SizedBox(height: 16),
                const SectionHeader(title: 'NETWORK', icon: Icons.hub_outlined),
                const _NetworkOverviewCard(),
                const SizedBox(height: 8),
                StatusCard(
                  accentColor: AppColors.info,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
                  child: ActionTile(
                    title: 'Live operations',
                    subtitle: 'Per-store progress, pause and stop',
                    icon: Icons.monitor_heart_outlined,
                    color: AppColors.info,
                    onTap: () => context.pushNamed<void>(AppRoutes.syncLive),
                  ),
                ),
              ],
              const SizedBox(height: 16),
              const SectionHeader(title: 'DETAILS', icon: Icons.tune_rounded),
              StatusCard(
                accentColor: AppColors.rule,
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
                child: Column(
                  children: [
                    ActionTile(
                      title: 'Entities',
                      subtitle: 'Record counts and last sync per entity',
                      icon: Icons.dataset_outlined,
                      color: AppColors.accent,
                      onTap: () => _showEntitiesSheet(context, ref),
                    ),
                    const Divider(height: 1),
                    ActionTile(
                      title: 'Operation queue',
                      subtitle: 'Pending, in-flight and dead-lettered ops',
                      icon: Icons.list_alt_rounded,
                      color: AppColors.warning,
                      onTap: () => _showQueueSheet(context, ref),
                    ),
                    const Divider(height: 1),
                    ActionTile(
                      title: 'Activity log',
                      subtitle: 'Recent sync events',
                      icon: Icons.receipt_long_outlined,
                      color: AppColors.info,
                      onTap: () => _showActivitySheet(context, ref),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      floatingActionButton: syncAsync.maybeWhen(
        data: (state) => FloatingActionButton.extended(
          onPressed: state.status.isBusy ? null : () => agent.triggerSync(),
          icon: AnimatedSwitcher(
            duration: const Duration(milliseconds: 200),
            child: Icon(
              state.status.isBusy ? Icons.sync_rounded : Icons.sync_rounded,
              key: ValueKey(state.status.isBusy),
            ),
          ),
          label: Text(state.status.isBusy ? 'Syncing…' : 'Sync now'),
        ),
        orElse: () => null,
      ),
    );
  }
}

Future<void> _showSheet(
  BuildContext context, {
  required String title,
  required IconData icon,
  required Widget child,
}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (context) => DraggableScrollableSheet(
      initialChildSize: 0.65,
      minChildSize: 0.4,
      maxChildSize: 0.92,
      expand: false,
      builder: (context, scrollController) {
        return Container(
          decoration: const BoxDecoration(
            color: AppColors.surfaceRaised,
            borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: Column(
            children: [
              const SizedBox(height: 10),
              Container(
                width: 36,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.rule,
                  borderRadius: BorderRadius.circular(999),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 14, 20, 4),
                child: Row(
                  children: [
                    Icon(icon, size: 18, color: AppColors.textMuted),
                    const SizedBox(width: 8),
                    Text(
                      title,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ],
                ),
              ),
              const Divider(height: 20),
              Expanded(
                child: ListView(
                  controller: scrollController,
                  padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
                  children: [child],
                ),
              ),
            ],
          ),
        );
      },
    ),
  );
}

void _showEntitiesSheet(BuildContext context, WidgetRef ref) {
  _showSheet(
    context,
    title: 'Entities',
    icon: Icons.dataset_outlined,
    child: Consumer(
      builder: (context, ref, _) {
        final meta = ref.watch(syncMetadataProvider);
        return meta.when(
          loading: () => const InlineLoading(),
          error: (e, _) => Text('$e'),
          data: (rows) => rows.isEmpty
              ? const EmptyState(
                  message: 'No entities have synced yet.',
                  icon: Icons.dataset_outlined,
                )
              : Column(
                  children: [
                    for (final r in rows)
                      InfoRow(
                        label: r.entity,
                        valueWidget: Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text(
                              '${r.recordCount} records',
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                            Text(
                              '${r.lastStatus} · ${formatRelative(r.lastSyncAt)}',
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
        );
      },
    ),
  );
}

void _showQueueSheet(BuildContext context, WidgetRef ref) {
  _showSheet(
    context,
    title: 'Operation queue',
    icon: Icons.list_alt_rounded,
    child: Consumer(
      builder: (context, ref, _) {
        final queue = ref.watch(syncQueueRowsProvider);
        return queue.when(
          loading: () => const InlineLoading(),
          error: (e, _) => Text('$e'),
          data: (rows) {
            final active =
                rows.where((r) => r.status != 'done').toList(growable: false);
            if (active.isEmpty) {
              return const EmptyState(
                message: 'Queue is empty.',
                icon: Icons.done_all_rounded,
              );
            }
            return Column(
              children: [
                for (final r in active.take(50))
                  InfoRow(
                    label: '${r.direction} · ${r.entity}',
                    valueWidget: _QueueBadge(row: r),
                  ),
              ],
            );
          },
        );
      },
    ),
  );
}

void _showActivitySheet(BuildContext context, WidgetRef ref) {
  _showSheet(
    context,
    title: 'Activity log',
    icon: Icons.receipt_long_outlined,
    child: Consumer(
      builder: (context, ref, _) {
        final history = ref.watch(syncHistoryProvider);
        return history.when(
          loading: () => const InlineLoading(),
          error: (e, _) => Text('$e'),
          data: (rows) => rows.isEmpty
              ? const EmptyState(
                  message: 'No activity yet.',
                  icon: Icons.history_rounded,
                )
              : Column(
                  children: [for (final r in rows.take(60)) _LogTile(row: r)],
                ),
        );
      },
    ),
  );
}

/// Platform-only: KPI strip + per-store status list from the Sync Control
/// Center endpoint. Network-wide, cross-store data — never shown to a
/// store-scoped session.
class _NetworkOverviewCard extends ConsumerWidget {
  const _NetworkOverviewCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(syncControlCenterProvider);
    return StatusCard(
      accentColor: AppColors.accent,
      child: async.when(
        loading: () => const InlineLoading(),
        error: (e, _) => Row(
          children: [
            const Icon(Icons.error_outline, size: 18, color: AppColors.danger),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                'Network data unavailable: $e',
                style: const TextStyle(color: AppColors.textMuted),
              ),
            ),
            TextButton(
              onPressed: () => ref.invalidate(syncControlCenterProvider),
              child: const Text('Retry'),
            ),
          ],
        ),
        data: (cc) => Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            MetricRow(
              tiles: [
                MetricTile(
                  label: 'Online',
                  value: '${cc.kpis.storesOnline}/${cc.kpis.totalStores}',
                  icon: Icons.wifi_rounded,
                  color: AppColors.success,
                ),
                MetricTile(
                  label: 'Running',
                  value: '${cc.kpis.syncRunning}',
                  icon: Icons.sync_rounded,
                  color: AppColors.accent,
                ),
                MetricTile(
                  label: 'Queued',
                  value: '${cc.kpis.queued}',
                  icon: Icons.hourglass_empty_rounded,
                  color: AppColors.warning,
                ),
                MetricTile(
                  label: 'Done today',
                  value: '${cc.kpis.completedToday}',
                  icon: Icons.check_circle_outline_rounded,
                  color: AppColors.info,
                ),
                MetricTile(
                  label: 'Failed today',
                  value: '${cc.kpis.failedToday}',
                  icon: Icons.error_outline_rounded,
                  color: cc.kpis.failedToday > 0
                      ? AppColors.danger
                      : AppColors.textMuted,
                ),
              ],
            ),
            if (cc.stores.isNotEmpty) ...[
              const Divider(height: 22),
              for (final store in cc.stores) _StoreSyncRow(store: store),
            ] else
              const EmptyState(message: 'No active stores on this platform.'),
          ],
        ),
      ),
    );
  }
}

class _StoreSyncRow extends StatelessWidget {
  const _StoreSyncRow({required this.store});
  final StoreSyncStatus store;

  Color get _statusColor => switch (store.status) {
        'Syncing' => AppColors.accent,
        'Online' => AppColors.success,
        _ => AppColors.textMuted,
      };

  @override
  Widget build(BuildContext context) {
    final color = _statusColor;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: ProgressRow(
        label: store.storeName,
        value: store.isSyncing ? null : (store.isOnline ? 1.0 : 0.0),
        trailingText: store.status,
        color: color,
      ),
    );
  }
}

class _QueueBadge extends StatelessWidget {
  const _QueueBadge({required this.row});
  final SyncQueueData row;

  @override
  Widget build(BuildContext context) {
    final color = switch (row.status) {
      'inFlight' => AppColors.accent,
      'deadLetter' => AppColors.danger,
      _ => row.attempts > 0 ? AppColors.warning : AppColors.textMuted,
    };
    final label =
        row.attempts > 0 ? '${row.status} (×${row.attempts})' : row.status;
    return StatusBadge(label: label, color: color, dense: true);
  }
}

class _LogTile extends StatelessWidget {
  const _LogTile({required this.row});
  final SyncHistoryData row;

  @override
  Widget build(BuildContext context) {
    final color = switch (row.level) {
      'error' => AppColors.danger,
      'warning' => AppColors.warning,
      'fine' => AppColors.textMuted,
      _ => AppColors.accent,
    };
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 5),
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  row.message,
                  style: const TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  '${row.category} · ${formatRelative(row.createdAt)}',
                  style: const TextStyle(
                      fontSize: 11.5, color: AppColors.textMuted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
