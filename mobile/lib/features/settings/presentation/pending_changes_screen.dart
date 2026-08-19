import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/core/widgets/offline_banner.dart';

/// Everything the user has changed that the server has not accepted yet.
///
/// This screen exists so "did my correction go through?" has an answer. Without
/// it the outbox is invisible, and an invisible queue is indistinguishable from
/// lost work — which is exactly the anxiety that makes people re-enter data.
class PendingChangesScreen extends ConsumerWidget {
  const PendingChangesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final entries = ref.watch(outboxOutstandingProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Pending changes'),
        actions: [
          IconButton(
            tooltip: 'Try now',
            icon: const Icon(Icons.sync_rounded),
            onPressed: () => ref.read(outboxCoordinatorProvider).drainNow(),
          ),
        ],
      ),
      body: Column(
        children: [
          const OfflineBanner(),
          Expanded(
            child: entries.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => Center(child: Text('$e')),
              data: (rows) => rows.isEmpty
                  ? const Center(
                      child: EmptyState(
                        icon: Icons.cloud_done_outlined,
                        message: 'Everything is synced.\nNo changes are '
                            'waiting, so it is safe to close the app.',
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: () async =>
                          ref.read(outboxCoordinatorProvider).drainNow(),
                      child: ListView.separated(
                        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
                        itemCount: rows.length,
                        separatorBuilder: (_, __) => const Divider(height: 20),
                        itemBuilder: (_, i) => _EntryTile(entry: rows[i]),
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _EntryTile extends ConsumerWidget {
  const _EntryTile({required this.entry});

  final OutboxEntry entry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = entry.parsedStatus;
    final stuck = status == OutboxStatus.deadLetter;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              stuck ? Icons.error_outline_rounded : Icons.schedule_rounded,
              size: 18,
              color: stuck ? AppColors.danger : AppColors.warningInk,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                entry.summary ?? entry.kind,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
            StatusBadge(
              label: stuck ? 'Needs you' : 'Waiting',
              color: stuck ? AppColors.danger : AppColors.warning,
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          _detail(entry, stuck),
          style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
        ),
        if (stuck) ...[
          const SizedBox(height: 10),
          Row(
            children: [
              // §3.8: a themed button in a Row needs a real minimumSize, or it
              // asserts at paint time with an infinite width.
              OutlinedButton(
                style: OutlinedButton.styleFrom(
                  minimumSize: const Size(0, 40),
                ),
                onPressed: () async {
                  await ref.read(outboxRepositoryProvider).retryNow(entry.id);
                  await ref.read(outboxCoordinatorProvider).drainNow();
                },
                child: const Text('Try again'),
              ),
              const SizedBox(width: 10),
              TextButton(
                style: TextButton.styleFrom(
                  minimumSize: const Size(0, 40),
                  foregroundColor: AppColors.danger,
                ),
                onPressed: () => _confirmDiscard(context, ref),
                child: const Text('Discard'),
              ),
            ],
          ),
        ],
      ],
    );
  }

  String _detail(OutboxEntry entry, bool stuck) {
    if (stuck) {
      return entry.lastError ??
          'This change could not be sent after several tries.';
    }
    if (entry.attemptCount == 0) {
      return 'Will be sent when you are back online.';
    }
    return 'Tried ${entry.attemptCount} time'
        '${entry.attemptCount == 1 ? '' : 's'}. '
        '${entry.lastError ?? 'Will try again shortly.'}';
  }

  Future<void> _confirmDiscard(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Discard this change?'),
        // Named as permanent because it is: the edit exists nowhere else, so
        // discarding it is the one action on this screen that loses work.
        content: Text(
          '"${entry.summary ?? entry.kind}" will be thrown away and never '
          'reach the server. This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Keep it'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Discard'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(outboxRepositoryProvider).discard(entry.id);
  }
}
