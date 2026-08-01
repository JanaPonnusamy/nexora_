import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/sync/sync_state.dart';
import 'package:nexora_mobile/core/sync/sync_status.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';

/// Phase 3 — live view of the offline sync engine: status, progress, the
/// operation queue, per-entity metadata and the recent activity log.
class SyncStatusScreen extends ConsumerWidget {
  const SyncStatusScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final syncAsync = ref.watch(syncStateProvider);
    final agent = ref.watch(agentManagerProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Sync Status')),
      body: syncAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Sync unavailable: $e')),
        data: (state) => RefreshIndicator(
          onRefresh: () => agent.triggerSync(),
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
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
