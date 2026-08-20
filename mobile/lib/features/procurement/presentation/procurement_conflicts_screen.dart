import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/core/widgets/offline_banner.dart';
import 'package:nexora_mobile/features/procurement/application/purchase_workspace_providers.dart';
import 'package:nexora_mobile/features/procurement/domain/purchase_workspace_models.dart';

class ProcurementConflictsScreen extends ConsumerWidget {
  const ProcurementConflictsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final entries = ref.watch(outboxOutstandingProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Procurement conflicts')),
      body: Column(
        children: [
          const OfflineBanner(
            message: 'Reconnect to compare a queued change with the server.',
          ),
          Expanded(
            child: entries.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Center(child: Text('$error')),
              data: (all) {
                final rows = all
                    .where((entry) =>
                        entry.kind.startsWith('procurement.') &&
                        entry.parsedStatus == OutboxStatus.deadLetter)
                    .toList(growable: false);
                if (rows.isEmpty) {
                  return const Center(
                    child: EmptyState(
                      icon: Icons.rule_folder_outlined,
                      message: 'No procurement conflicts need a decision.',
                    ),
                  );
                }
                return ListView.separated(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
                  itemCount: rows.length,
                  separatorBuilder: (_, __) => const Divider(height: 20),
                  itemBuilder: (_, index) => _ConflictTile(entry: rows[index]),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ConflictTile extends ConsumerWidget {
  const _ConflictTile({required this.entry});

  final OutboxEntry entry;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Icon(Icons.sync_problem_rounded, color: AppColors.danger),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                entry.summary ?? entry.kind,
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
            const StatusBadge(
              label: 'Conflict',
              color: AppColors.danger,
              dense: true,
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text(
          entry.lastError ?? 'The server did not accept this queued change.',
          style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
        ),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          onPressed: () => _resolve(context, ref),
          icon: const Icon(Icons.compare_arrows_rounded),
          label: const Text('Resolve'),
        ),
      ],
    );
  }

  Future<void> _resolve(BuildContext context, WidgetRef ref) async {
    final payload = entry.decodedPayload;
    final tenantId = payload['tenantId'] as String?;
    final orderItemId = payload['orderItemId'] as String?;
    if (tenantId == null || orderItemId == null) return;
    final future = ref.read(purchaseWorkspaceApiProvider).item(
          tenantId: tenantId,
          orderItemId: orderItemId,
        );
    final choice = await showDialog<_Resolution>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Resolve queued change'),
        content: FutureBuilder<PurchaseWorkspaceItem>(
          future: future,
          builder: (_, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const SizedBox(
                height: 80,
                child: Center(child: CircularProgressIndicator()),
              );
            }
            if (snapshot.hasError || snapshot.data == null) {
              return const Text(
                'The latest server value could not be loaded. Reconnect and try again.',
              );
            }
            final item = snapshot.data!;
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.productName,
                    style: const TextStyle(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                Text('Server final quantity: ${item.finalQty.compact}'),
                Text('Server assigned quantity: ${item.assignedQty.compact}'),
                Text('Server remaining quantity: ${item.remainingQty.compact}'),
                const SizedBox(height: 8),
                Text(_queuedDescription(payload)),
                if (entry.lastError != null) ...[
                  const SizedBox(height: 8),
                  Text(entry.lastError!,
                      style: const TextStyle(color: AppColors.dangerInk)),
                ],
              ],
            );
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () =>
                Navigator.pop(dialogContext, _Resolution.keepServer),
            child: const Text('Keep server'),
          ),
          FilledButton(
            onPressed: () =>
                Navigator.pop(dialogContext, _Resolution.applyMine),
            child: const Text('Apply mine'),
          ),
        ],
      ),
    );
    if (choice == null) return;
    if (choice == _Resolution.keepServer) {
      await ref.read(outboxRepositoryProvider).discard(entry.id);
    } else {
      await ref.read(outboxRepositoryProvider).retryNow(entry.id);
      await ref.read(outboxCoordinatorProvider).drainNow();
    }
  }

  String _queuedDescription(Map<String, dynamic> payload) {
    if (entry.kind == PurchaseOutboxKinds.finalQty) {
      return 'Your queued final quantity: ${payload['finalQty']}';
    }
    if (entry.kind == PurchaseOutboxKinds.assign) {
      return 'Your queued assignment: ${payload['qty']} to '
          '${payload['supplierCode']}';
    }
    if (entry.kind == PurchaseOutboxKinds.skip) {
      return 'Your queued action: Skip';
    }
    if (entry.kind == PurchaseOutboxKinds.restore) {
      return 'Your queued action: Restore';
    }
    return 'Your queued action: ${entry.kind}';
  }
}

enum _Resolution { keepServer, applyMine }

extension on double {
  String get compact =>
      this == roundToDouble() ? toInt().toString() : toString();
}
