import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';
import 'package:nexora_mobile/features/sync/application/sync_live_providers.dart';
import 'package:nexora_mobile/features/sync/data/sync_live_models.dart';
import 'package:nexora_mobile/features/sync/presentation/widgets/live_execution_card.dart';

/// Network-wide live sync operations: which stores are syncing right now, how
/// far along, and the controls to pause or stop them.
///
/// Online-only on purpose. A stale answer to "is store 7 syncing?" is worse
/// than no answer, so nothing here is cached and going offline shows an
/// explicit empty state rather than the last frame.
class SyncLiveScreen extends ConsumerStatefulWidget {
  const SyncLiveScreen({super.key});

  @override
  ConsumerState<SyncLiveScreen> createState() => _SyncLiveScreenState();
}

class _SyncLiveScreenState extends ConsumerState<SyncLiveScreen> {
  /// Store ids with a control action in flight.
  final Set<String> _busy = {};

  Future<void> _control(
    LiveSyncExecution execution,
    SyncControlAction action,
  ) async {
    if (action == SyncControlAction.stop && !await _confirmStop(execution)) {
      return;
    }
    if (!mounted) return;

    final messenger = ScaffoldMessenger.of(context);
    setState(() => _busy.add(execution.storeId));
    try {
      final result = await ref.read(syncLiveServiceProvider).control(
        storeIds: [execution.storeId],
        action: action,
      );
      // Report what the server actually changed. `control_stores` loops per
      // store and can affect nothing at all if the execution finished between
      // the poll and the tap.
      messenger.showSnackBar(
        SnackBar(
          content: Text(
            result.affected == 0
                ? 'Nothing to ${action.label.toLowerCase()} — it had already '
                    'finished.'
                : '${action.label}d ${execution.label}.',
          ),
        ),
      );
      ref.invalidate(syncLiveProvider);
    } on ApiException catch (e) {
      messenger.showSnackBar(
        SnackBar(
          content: Text(e.message),
          backgroundColor: AppColors.dangerSunk,
        ),
      );
    } finally {
      if (mounted) setState(() => _busy.remove(execution.storeId));
    }
  }

  Future<bool> _confirmStop(LiveSyncExecution execution) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Stop the sync for ${execution.label}?'),
        content: const Text(
          'The execution is cancelled where it stands. Rows already sent are '
          'kept, but the remaining tables are not synced until the next run.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep syncing'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: TextButton.styleFrom(foregroundColor: AppColors.danger),
            child: const Text('Stop'),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }

  void _showHistory() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.surfaceRaised,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const _HistorySheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final live = ref.watch(syncLiveProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Live operations'),
        actions: [
          IconButton(
            onPressed: _showHistory,
            icon: const Icon(Icons.history_rounded),
            tooltip: 'Recent executions',
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(syncLiveProvider);
          await ref.read(syncLiveProvider.future);
        },
        child: live.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => _Scrollable(
            child: EmptyState(
              message: e is ApiException && e.isNetwork
                  ? 'Live status needs a connection.\nIt is never shown from '
                      'cache — a stale answer would be worse than none.'
                  : 'Could not read live status.\n$e',
              icon: Icons.cloud_off_rounded,
            ),
          ),
          data: (executions) => executions.isEmpty
              ? const _Scrollable(child: _IdleState())
              : ListView.builder(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
                  itemCount: executions.length + 1,
                  itemBuilder: (context, index) {
                    if (index == 0) return _Summary(executions: executions);
                    final execution = executions[index - 1];
                    return LiveExecutionCard(
                      execution: execution,
                      busy: _busy.contains(execution.storeId),
                      onControl: (action) => _control(execution, action),
                    );
                  },
                ),
        ),
      ),
    );
  }
}

class _Summary extends StatelessWidget {
  const _Summary({required this.executions});

  final List<LiveSyncExecution> executions;

  @override
  Widget build(BuildContext context) {
    final paused = executions.where((e) => e.isPaused).length;
    final running = executions.length - paused;

    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        children: [
          Expanded(
            child: Text(
              running > 0
                  ? '$running store${running == 1 ? '' : 's'} syncing'
                  : '$paused paused',
              style: const TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: AppColors.info,
              ),
            ),
          ),
          if (paused > 0 && running > 0)
            Text(
              '$paused paused',
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.warningInk,
              ),
            ),
        ],
      ),
    );
  }
}

/// An idle network is the normal state, not an error — say so plainly.
class _IdleState extends ConsumerWidget {
  const _IdleState();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final online = ref.watch(connectivityServiceProvider).lastKnown.isOnline;
    return EmptyState(
      message: online
          ? 'No sync running anywhere right now.\nThis refreshes every few '
              'seconds while the screen is open.'
          : 'Offline. Live status is not cached, so there is nothing to show '
              'until you reconnect.',
      icon:
          online ? Icons.check_circle_outline_rounded : Icons.cloud_off_rounded,
    );
  }
}

class _HistorySheet extends ConsumerWidget {
  const _HistorySheet();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final history = ref.watch(syncHistoryProvider(null));

    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.7,
      maxChildSize: 0.9,
      builder: (context, controller) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(20, 4, 20, 8),
            child: Text(
              'Recent executions',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
          ),
          Expanded(
            child: history.when(
              loading: () => const InlineLoading(height: 120),
              error: (e, _) => EmptyState(
                message: 'Could not load history.\n$e',
                icon: Icons.error_outline_rounded,
              ),
              data: (entries) => entries.isEmpty
                  ? const EmptyState(
                      message: 'No executions recorded yet.',
                      icon: Icons.history_rounded,
                    )
                  : ListView.separated(
                      controller: controller,
                      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                      itemCount: entries.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, i) =>
                          _HistoryRow(entry: entries[i]),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HistoryRow extends StatelessWidget {
  const _HistoryRow({required this.entry});

  final SyncHistoryEntry entry;

  @override
  Widget build(BuildContext context) {
    final tone = entry.isFailure
        ? AppColors.danger
        : entry.isSuccess
            ? AppColors.success
            : AppColors.textMuted;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Icon(
              entry.isFailure
                  ? Icons.error_outline_rounded
                  : entry.isSuccess
                      ? Icons.check_circle_outline_rounded
                      : Icons.remove_circle_outline_rounded,
              size: 16,
              color: tone,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entry.label,
                  style: const TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w600,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  _detail(),
                  style: const TextStyle(
                    fontSize: 11.5,
                    color: AppColors.textMuted,
                  ),
                ),
                if (entry.errorMessage != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(
                      entry.errorMessage!,
                      style: const TextStyle(
                        fontSize: 11.5,
                        color: AppColors.dangerInk,
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            formatRelative(entry.completedAt ?? entry.startedAt),
            style: const TextStyle(fontSize: 11, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }

  String _detail() {
    final parts = <String>[
      entry.status,
      if (entry.syncMode != null) entry.syncMode!,
      if (entry.rowsSynced > 0) '${entry.rowsSynced} rows',
      if (entry.duration != null) _short(entry.duration!),
    ];
    return parts.join(' · ');
  }

  static String _short(Duration d) {
    if (d.inSeconds < 60) return '${d.inSeconds}s';
    if (d.inMinutes < 60) return '${d.inMinutes}m';
    return '${d.inHours}h ${d.inMinutes.remainder(60)}m';
  }
}

/// Empty and error states must still be draggable, or pull-to-refresh is
/// unreachable — the only way back from a transient failure.
class _Scrollable extends StatelessWidget {
  const _Scrollable({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: Padding(padding: const EdgeInsets.all(32), child: child),
          ),
        ),
      ),
    );
  }
}
