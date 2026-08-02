import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/sync/sync_state.dart';
import 'package:nexora_mobile/core/sync/sync_status.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';
import 'package:nexora_mobile/features/sync/data/sync_control_center.dart';

/// Live view of the sync engine. For every user this shows the device's own
/// offline sync (status, progress, operation queue, entities, activity log).
/// Platform users additionally see a **Network** overview — every store's live
/// sync status — sourced from the same read-only endpoint the HO web console's
/// Sync Control Center uses (`GET /api/sync/control-center`).
class SyncStatusScreen extends ConsumerWidget {
  const SyncStatusScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final syncAsync = ref.watch(syncStateProvider);
    final agent = ref.watch(agentManagerProvider);
    final isPlatformUser = ref.watch(isPlatformUserProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Sync Status')),
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
            padding: const EdgeInsets.all(16),
            children: [
              if (isPlatformUser) ...[
                const _NetworkOverviewCard(),
                const SizedBox(height: 12),
              ],
              _OverviewCard(state: state),
              const SizedBox(height: 12),
              _MetadataCard(),
              const SizedBox(height: 12),
              _QueueCard(),
              const SizedBox(height: 12),
              _ActivityCard(),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
      floatingActionButton: syncAsync.maybeWhen(
        data: (state) => FloatingActionButton.extended(
          onPressed: state.status.isBusy ? null : () => agent.triggerSync(),
          icon: const Icon(Icons.sync),
          label: Text(state.status.isBusy ? 'Syncing…' : 'Sync now'),
        ),
        orElse: () => null,
      ),
    );
  }
}

/// Platform-only: KPI strip + per-store status grid from the Sync Control
/// Center endpoint. This is network-wide, cross-store data — never shown to a
/// store-scoped session.
class _NetworkOverviewCard extends ConsumerWidget {
  const _NetworkOverviewCard();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(syncControlCenterProvider);
    return SectionCard(
      title: 'Network',
      icon: Icons.hub_outlined,
      trailing: IconButton(
        tooltip: 'Refresh',
        visualDensity: VisualDensity.compact,
        icon: const Icon(Icons.refresh_rounded, size: 20),
        onPressed: () => ref.invalidate(syncControlCenterProvider),
      ),
      children: [
        async.when(
          loading: () => const _Loading(),
          error: (e, _) => Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Row(
              children: [
                const Icon(Icons.error_outline, size: 18, color: AppColors.error),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Network data unavailable: $e',
                      style: const TextStyle(color: AppColors.slate),),
                ),
                TextButton(
                  onPressed: () => ref.invalidate(syncControlCenterProvider),
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
          data: (cc) => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _KpiRow(kpis: cc.kpis),
              const SizedBox(height: 4),
              const Divider(height: 24),
              for (final store in cc.stores) _StoreSyncRow(store: store),
              if (cc.stores.isEmpty)
                const _Empty('No active stores on this platform.'),
            ],
          ),
        ),
      ],
    );
  }
}

class _KpiRow extends StatelessWidget {
  const _KpiRow({required this.kpis});
  final SyncKpis kpis;

  @override
  Widget build(BuildContext context) {
    final items = [
      (
        'Online',
        '${kpis.storesOnline}/${kpis.totalStores}',
        Icons.wifi_rounded,
        AppColors.success,
      ),
      ('Running', '${kpis.syncRunning}', Icons.sync_rounded, AppColors.primary),
      ('Queued', '${kpis.queued}', Icons.hourglass_empty_rounded, AppColors.warning),
      (
        'Done today',
        '${kpis.completedToday}',
        Icons.check_circle_outline_rounded,
        AppColors.accent,
      ),
      (
        'Failed today',
        '${kpis.failedToday}',
        Icons.error_outline_rounded,
        kpis.failedToday > 0 ? AppColors.error : AppColors.slate,
      ),
    ];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final item in items) ...[
            _KpiChip(
              label: item.$1,
              value: item.$2,
              icon: item.$3,
              color: item.$4,
            ),
            const SizedBox(width: 10),
          ],
        ],
      ),
    );
  }
}

class _KpiChip extends StatelessWidget {
  const _KpiChip({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 96,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.w800,
              color: color,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: const TextStyle(fontSize: 11.5, color: AppColors.slate),
          ),
        ],
      ),
    );
  }
}

class _StoreSyncRow extends StatelessWidget {
  const _StoreSyncRow({required this.store});
  final StoreSyncStatus store;

  Color get _statusColor => switch (store.status) {
        'Syncing' => AppColors.primary,
        'Online' => AppColors.success,
        _ => AppColors.slate,
      };

  @override
  Widget build(BuildContext context) {
    final color = _statusColor;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      store.storeName,
                      style: const TextStyle(fontWeight: FontWeight.w600),
                      overflow: TextOverflow.ellipsis,
                    ),
                    Text(
                      '${store.storeCode} · ${formatRelative(store.lastSync)}',
                      style: const TextStyle(
                          fontSize: 11.5, color: AppColors.slate,),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              StatusPill(label: store.status, color: color),
            ],
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              // Syncing → animated/indeterminate. Online+idle → full ("up to
              // date"). Offline → empty ("stalled").
              value: store.isSyncing ? null : (store.isOnline ? 1.0 : 0.0),
              minHeight: 5,
              backgroundColor: color.withValues(alpha: 0.12),
              valueColor: AlwaysStoppedAnimation(color),
            ),
          ),
        ],
      ),
    );
  }
}

Color _statusColor(SyncStatus s) => switch (s) {
      SyncStatus.success => AppColors.success,
      SyncStatus.failed => AppColors.error,
      SyncStatus.offline => AppColors.slate,
      SyncStatus.paused => AppColors.warning,
      _ => AppColors.primary,
    };

class _OverviewCard extends StatelessWidget {
  const _OverviewCard({required this.state});
  final SyncState state;

  @override
  Widget build(BuildContext context) {
    final color = _statusColor(state.status);
    return SectionCard(
      title: 'Engine',
      icon: Icons.sync_rounded,
      trailing: StatusPill(label: state.status.label, color: color),
      children: [
        if (state.status.isBusy) ...[
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: state.progress == 0 ? null : state.progress,
              minHeight: 8,
            ),
          ),
          const SizedBox(height: 8),
        ],
        InfoRow(
          label: 'Network',
          valueWidget: StatusPill(
            label: state.online ? 'Online' : 'Offline',
            color: state.online ? AppColors.success : AppColors.slate,
          ),
        ),
        InfoRow(label: 'Pending operations', value: '${state.pending}'),
        InfoRow(label: 'Completed (last run)', value: '${state.completed}'),
        InfoRow(label: 'Failed (last run)', value: '${state.failed}'),
        if (state.currentEntity != null)
          InfoRow(label: 'Current', value: state.currentEntity),
        InfoRow(label: 'Last run', value: formatRelative(state.lastRunAt)),
        InfoRow(
            label: 'Last success', value: formatRelative(state.lastSuccessAt),),
        if (state.lastError != null)
          InfoRow(label: 'Last error', value: state.lastError),
      ],
    );
  }
}

class _MetadataCard extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final meta = ref.watch(syncMetadataProvider);
    return SectionCard(
      title: 'Entities',
      icon: Icons.dataset_outlined,
      children: [
        meta.when(
          loading: () => const _Loading(),
          error: (e, _) => Text('$e'),
          data: (rows) => rows.isEmpty
              ? const _Empty('No entities have synced yet.')
              : Column(
                  children: [
                    for (final r in rows)
                      InfoRow(
                        label: r.entity,
                        valueWidget: Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Text('${r.recordCount} records',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600,),),
                            Text(
                              '${r.lastStatus} · ${formatRelative(r.lastSyncAt)}',
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
    );
  }
}

class _QueueCard extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final queue = ref.watch(syncQueueRowsProvider);
    return SectionCard(
      title: 'Operation queue',
      icon: Icons.list_alt_rounded,
      children: [
        queue.when(
          loading: () => const _Loading(),
          error: (e, _) => Text('$e'),
          data: (rows) {
            final active =
                rows.where((r) => r.status != 'done').toList(growable: false);
            if (active.isEmpty) {
              return const _Empty('Queue is empty.');
            }
            return Column(
              children: [
                for (final r in active.take(20))
                  InfoRow(
                    label: '${r.direction} · ${r.entity}',
                    valueWidget: _QueueBadge(row: r),
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _QueueBadge extends StatelessWidget {
  const _QueueBadge({required this.row});
  final SyncQueueData row;

  @override
  Widget build(BuildContext context) {
    final color = switch (row.status) {
      'inFlight' => AppColors.primary,
      'deadLetter' => AppColors.error,
      _ => row.attempts > 0 ? AppColors.warning : AppColors.slate,
    };
    final label =
        row.attempts > 0 ? '${row.status} (×${row.attempts})' : row.status;
    return StatusPill(label: label, color: color);
  }
}

class _ActivityCard extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(syncHistoryProvider);
    return SectionCard(
      title: 'Activity log',
      icon: Icons.receipt_long_outlined,
      children: [
        history.when(
          loading: () => const _Loading(),
          error: (e, _) => Text('$e'),
          data: (rows) => rows.isEmpty
              ? const _Empty('No activity yet.')
              : Column(
                  children: [for (final r in rows.take(40)) _LogTile(row: r)],
                ),
        ),
      ],
    );
  }
}

class _LogTile extends StatelessWidget {
  const _LogTile({required this.row});
  final SyncHistoryData row;

  @override
  Widget build(BuildContext context) {
    final color = switch (row.level) {
      'error' => AppColors.error,
      'warning' => AppColors.warning,
      'fine' => AppColors.slate,
      _ => AppColors.primary,
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
                Text(row.message,
                    style: const TextStyle(
                        fontSize: 13.5, fontWeight: FontWeight.w500,),),
                Text(
                  '${row.category} · ${formatRelative(row.createdAt)}',
                  style:
                      const TextStyle(fontSize: 11.5, color: AppColors.slate),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Loading extends StatelessWidget {
  const _Loading();
  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Center(
          child: SizedBox(
            height: 20,
            width: 20,
            child: CircularProgressIndicator(strokeWidth: 2.2),
          ),
        ),
      );
}

class _Empty extends StatelessWidget {
  const _Empty(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Text(text, style: const TextStyle(color: AppColors.slate)),
      );
}
