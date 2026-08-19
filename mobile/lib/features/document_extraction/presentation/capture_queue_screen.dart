import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_controller.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_entry.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_export_controller.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/capture_queue_card.dart';

/// Everything captured on this device and where it has got to.
///
/// The queue is the honest answer to "did my invoice go through?", so it shows
/// the states the rest of the app hides: backing off, given up, failed on the
/// server. Each of those comes with the one button that resolves it.
class CaptureQueueScreen extends ConsumerStatefulWidget {
  const CaptureQueueScreen({super.key});

  @override
  ConsumerState<CaptureQueueScreen> createState() => _CaptureQueueScreenState();
}

class _CaptureQueueScreenState extends ConsumerState<CaptureQueueScreen> {
  /// Batch ids with an action in flight, so one card's spinner does not lock
  /// the whole list.
  final Set<int> _busy = {};

  Future<void> _run(
    CaptureQueueEntry entry,
    Future<QueueActionResult> Function() action,
  ) async {
    if (_busy.contains(entry.batchId)) return;
    setState(() => _busy.add(entry.batchId));
    final messenger = ScaffoldMessenger.of(context);
    try {
      final result = await action();
      messenger.showSnackBar(
        SnackBar(
          content: Text(result.message),
          backgroundColor: result.ok ? null : AppColors.dangerSunk,
        ),
      );
    } finally {
      if (mounted) setState(() => _busy.remove(entry.batchId));
    }
  }

  Future<void> _onAction(CaptureQueueEntry entry, QueueAction action) async {
    final controller = ref.read(captureQueueControllerProvider);
    switch (action) {
      case QueueAction.retryUpload:
        await _run(entry, () => controller.retryUpload(entry));
      case QueueAction.retryPipeline:
        await _run(entry, () => controller.retryPipeline(entry));
      case QueueAction.delete:
        if (await _confirmDelete(entry)) {
          await _run(entry, () => controller.delete(entry));
        }
      case QueueAction.review:
        final importId = entry.importId;
        if (importId == null) {
          // Only reachable if a row reports a reviewable stage without ever
          // having been accepted by the server — there is nothing on the
          // server to review, so say that rather than opening an empty screen.
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('This document has not reached the server yet.'),
            ),
          );
          return;
        }
        await context.push(
          AppRoutes.documentReviewLocation(importId, batchId: entry.batchId),
        );
      case QueueAction.export:
        await _export([entry]);
    }
  }

  /// Builds one workbook covering [entries] and shares it.
  ///
  /// Batched deliberately: the export contract puts every selected invoice
  /// into a single five-sheet workbook, and an accountant would rather receive
  /// one file for the morning than seven.
  Future<void> _export(List<CaptureQueueEntry> entries) async {
    final exportable =
        entries.where((e) => e.importId != null).toList(growable: false);
    if (exportable.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Nothing here has been saved for export yet.'),
        ),
      );
      return;
    }

    final messenger = ScaffoldMessenger.of(context);
    setState(() => _busy.addAll(exportable.map((e) => e.batchId)));
    try {
      final outcome = await ref
          .read(documentExportControllerProvider)
          .exportAndShare(
            importIds:
                exportable.map((e) => e.importId!).toList(growable: false),
            batchIds: exportable.map((e) => e.batchId).toList(growable: false),
            subject: exportable.length == 1
                ? 'Invoice #${exportable.single.importId}'
                : '${exportable.length} invoices',
            sharePositionOrigin: _shareOrigin(),
          );
      messenger.showSnackBar(
        SnackBar(
          content: Text(outcome.message),
          backgroundColor: outcome.ok ? null : AppColors.dangerSunk,
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _busy.removeAll(exportable.map((e) => e.batchId)));
      }
    }
  }

  /// Anchor for the iPad share popover, which throws without one. Falls back
  /// to null on a phone, where the sheet slides up from the bottom regardless.
  Rect? _shareOrigin() {
    final box = context.findRenderObject();
    if (box is! RenderBox || !box.hasSize) return null;
    return box.localToGlobal(Offset.zero) & box.size;
  }

  Future<bool> _confirmDelete(CaptureQueueEntry entry) async {
    final onServer = entry.importId != null;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this document?'),
        content: Text(
          onServer
              ? 'The ${entry.pageCount} captured page'
                  '${entry.pageCount == 1 ? '' : 's'} and the extracted data on '
                  'the server will both be deleted. This cannot be undone.'
              : 'The ${entry.pageCount} captured page'
                  '${entry.pageCount == 1 ? '' : 's'} will be deleted. It has '
                  'not been uploaded, so there is no other copy.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Keep'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: TextButton.styleFrom(foregroundColor: AppColors.danger),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }

  @override
  Widget build(BuildContext context) {
    final entries = ref.watch(captureQueueEntriesProvider);

    final pending = entries.valueOrNull
            ?.where((e) => e.stage == QueueStage.saved)
            .toList(growable: false) ??
        const <CaptureQueueEntry>[];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Capture queue'),
        actions: [
          PopupMenuButton<String>(
            onSelected: (value) async {
              switch (value) {
                case 'export-all':
                  await _export(pending);
                case 'reclaim':
                  final messenger = ScaffoldMessenger.of(context);
                  final result = await ref
                      .read(captureQueueControllerProvider)
                      .reclaimSpace();
                  messenger
                      .showSnackBar(SnackBar(content: Text(result.message)));
              }
            },
            itemBuilder: (_) => [
              if (pending.isNotEmpty)
                PopupMenuItem(
                  value: 'export-all',
                  // The common intent: one workbook for everything reviewed
                  // this morning, rather than a file per invoice.
                  child: Text(
                    'Export ${pending.length} saved '
                    'invoice${pending.length == 1 ? '' : 's'}',
                  ),
                ),
              const PopupMenuItem(
                value: 'reclaim',
                child: Text('Free up space'),
              ),
            ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(captureQueueControllerProvider).refresh(),
        child: entries.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => _Scrollable(
            child: EmptyState(
              message: 'Could not read the capture queue.\n$e',
              icon: Icons.error_outline_rounded,
            ),
          ),
          data: (list) => list.isEmpty
              ? const _Scrollable(
                  child: EmptyState(
                    message: 'Nothing captured yet.\nDocuments you photograph '
                        'appear here until they are exported.',
                    icon: Icons.inbox_outlined,
                  ),
                )
              : ListView.builder(
                  // Always scrollable, so pull-to-refresh works on a short list.
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
                  itemCount: list.length + 1,
                  itemBuilder: (context, index) {
                    if (index == 0) return _Summary(entries: list);
                    final entry = list[index - 1];
                    return CaptureQueueCard(
                      entry: entry,
                      busy: _busy.contains(entry.batchId),
                      onAction: (action) => _onAction(entry, action),
                    );
                  },
                ),
        ),
      ),
    );
  }
}

/// Leads the list with whatever needs a person, because that is the only
/// reason to be on this screen rather than capturing.
class _Summary extends StatelessWidget {
  const _Summary({required this.entries});

  final List<CaptureQueueEntry> entries;

  @override
  Widget build(BuildContext context) {
    final needsUser = entries.where((e) => e.needsUser).length;
    final inFlight = entries.where((e) => e.isBusy).length;
    final waiting = entries
        .where(
          (e) =>
              e.stage == QueueStage.waiting || e.stage == QueueStage.retrying,
        )
        .length;
    // Saved but not yet in a workbook. Not "attention" — nothing is wrong —
    // but calling it up to date would hide the last step of the job.
    final toExport = entries.where((e) => e.stage == QueueStage.saved).length;

    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        children: [
          Expanded(
            child: Text(
              needsUser > 0
                  ? '$needsUser need${needsUser == 1 ? 's' : ''} your attention'
                  : inFlight > 0
                      ? 'Processing $inFlight document'
                          '${inFlight == 1 ? '' : 's'}'
                      : waiting > 0
                          ? '$waiting waiting to upload'
                          : toExport > 0
                              ? '$toExport ready to export'
                              : 'Everything is up to date',
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color:
                    needsUser > 0 ? AppColors.warningInk : AppColors.textMuted,
              ),
            ),
          ),
          Text(
            '${entries.length} total',
            style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

/// Empty and error states still have to be draggable, or pull-to-refresh —
/// the only way back from a transient error — is unreachable.
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
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: child,
            ),
          ),
        ),
      ),
    );
  }
}
