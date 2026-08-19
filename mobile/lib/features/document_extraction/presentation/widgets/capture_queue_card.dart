import 'dart:io';

import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_entry.dart';

/// One document in the capture queue.
///
/// A card rather than a list row because every state here has something to
/// say — why it stopped, when it retries, what to do next — and a one-line
/// row would push all of that behind a tap.
class CaptureQueueCard extends StatelessWidget {
  const CaptureQueueCard({
    super.key,
    required this.entry,
    required this.onAction,
    this.busy = false,
  });

  final CaptureQueueEntry entry;

  /// Null for actions the entry does not offer.
  final void Function(QueueAction action) onAction;

  /// True while one of this card's actions is running.
  final bool busy;

  static Color colorFor(QueueTone tone) => switch (tone) {
        QueueTone.neutral => AppColors.textMuted,
        QueueTone.info => AppColors.info,
        QueueTone.accent => AppColors.accent,
        QueueTone.success => AppColors.success,
        QueueTone.warning => AppColors.warning,
        QueueTone.danger => AppColors.danger,
      };

  static IconData _iconFor(QueueStage stage) => switch (stage) {
        QueueStage.waiting => Icons.schedule_rounded,
        QueueStage.retrying => Icons.replay_rounded,
        QueueStage.stopped => Icons.pause_circle_outline_rounded,
        QueueStage.processing => Icons.autorenew_rounded,
        QueueStage.readyToReview => Icons.fact_check_outlined,
        QueueStage.saved => Icons.check_circle_outline_rounded,
        QueueStage.exported => Icons.table_view_rounded,
        QueueStage.failed => Icons.error_outline_rounded,
      };

  @override
  Widget build(BuildContext context) {
    final tone = colorFor(entry.tone);

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: StatusCard(
        accentColor: tone,
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _Thumbnail(path: entry.thumbnailPath, tone: tone),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              entry.title,
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.w700,
                              ),
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          StatusBadge(
                            label: entry.statusLabel,
                            color: tone,
                            icon: _iconFor(entry.stage),
                            dense: true,
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        '${formatRelative(entry.capturedAt)} · '
                        '${entry.sizeLabel}',
                        style: const TextStyle(
                          fontSize: 11.5,
                          color: AppColors.textMuted,
                        ),
                      ),
                      if (entry.flaggedPages > 0)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: InfoChip(
                            // Surfaced here so a poor extraction has an
                            // explanation the user can act on, instead of
                            // reading as the server being wrong.
                            label: '${entry.flaggedPages} page'
                                '${entry.flaggedPages == 1 ? '' : 's'} '
                                'flagged at capture',
                            icon: Icons.info_outline_rounded,
                            color: AppColors.warning,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
            if (entry.detail != null) ...[
              const SizedBox(height: 10),
              Text(
                entry.detail!,
                style: const TextStyle(
                  fontSize: 12.5,
                  height: 1.35,
                  color: AppColors.textSoft,
                ),
              ),
            ],
            if (entry.isBusy || busy) ...[
              const SizedBox(height: 10),
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  minHeight: 4,
                  backgroundColor: tone.withValues(alpha: 0.12),
                  valueColor: AlwaysStoppedAnimation(tone),
                ),
              ),
            ],
            _actions(tone),
          ],
        ),
      ),
    );
  }

  Widget _actions(Color tone) {
    final buttons = <Widget>[
      if (entry.can(QueueAction.export))
        _QueueButton(
          // Leads on a saved document: reviewing it again is possible but
          // exporting is the step that is actually outstanding. Re-sharing an
          // already-exported workbook is secondary, hence the softer style.
          label: entry.stage == QueueStage.exported ? 'Share again' : 'Export',
          icon: Icons.ios_share_rounded,
          color: tone,
          filled: entry.stage == QueueStage.saved,
          onPressed: busy ? null : () => onAction(QueueAction.export),
        ),
      if (entry.can(QueueAction.review))
        _QueueButton(
          label: 'Review',
          icon: Icons.fact_check_outlined,
          color: tone,
          filled: entry.stage == QueueStage.readyToReview,
          onPressed: busy ? null : () => onAction(QueueAction.review),
        ),
      if (entry.can(QueueAction.retryUpload))
        _QueueButton(
          label: 'Upload now',
          icon: Icons.cloud_upload_outlined,
          color: tone,
          filled: entry.stage == QueueStage.stopped,
          onPressed: busy ? null : () => onAction(QueueAction.retryUpload),
        ),
      if (entry.can(QueueAction.retryPipeline))
        _QueueButton(
          label: 'Try again',
          icon: Icons.replay_rounded,
          color: tone,
          filled: true,
          onPressed: busy ? null : () => onAction(QueueAction.retryPipeline),
        ),
      if (entry.can(QueueAction.delete))
        _QueueButton(
          label: 'Delete',
          icon: Icons.delete_outline_rounded,
          color: AppColors.textMuted,
          onPressed: busy ? null : () => onAction(QueueAction.delete),
        ),
    ];

    if (buttons.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Wrap(spacing: 8, runSpacing: 4, children: buttons),
    );
  }
}

/// Compact action. Explicit `minimumSize` because the app theme gives buttons
/// `Size.fromHeight`, i.e. an infinite minimum width, which asserts the moment
/// one is laid out inside a Row or Wrap.
class _QueueButton extends StatelessWidget {
  const _QueueButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onPressed,
    this.filled = false,
  });

  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback? onPressed;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    const style = ButtonStyle(
      minimumSize: WidgetStatePropertyAll(Size(0, 38)),
      padding: WidgetStatePropertyAll(
        EdgeInsets.symmetric(horizontal: 14),
      ),
      textStyle: WidgetStatePropertyAll(
        TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
      ),
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );

    if (filled) {
      return FilledButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 16),
        label: Text(label),
        style: style.copyWith(
          backgroundColor: WidgetStatePropertyAll(
            color.withValues(alpha: 0.16),
          ),
          foregroundColor: WidgetStatePropertyAll(color),
        ),
      );
    }
    return TextButton.icon(
      onPressed: onPressed,
      icon: Icon(icon, size: 16),
      label: Text(label),
      style: style.copyWith(
        foregroundColor: WidgetStatePropertyAll(color),
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  const _Thumbnail({required this.path, required this.tone});

  final String? path;
  final Color tone;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 46,
      height: 58,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        color: AppColors.surfaceSunk,
        border: Border.all(color: AppColors.rule),
      ),
      clipBehavior: Clip.antiAlias,
      child: path == null
          // Exported documents have had their page images reclaimed, so a
          // missing file here is expected rather than a failure.
          ? const Icon(
              Icons.description_outlined,
              size: 18,
              color: AppColors.textMuted,
            )
          : Image.file(
              File(path!),
              fit: BoxFit.cover,
              cacheWidth: 138,
              gaplessPlayback: true,
              errorBuilder: (_, __, ___) => const Icon(
                Icons.description_outlined,
                size: 18,
                color: AppColors.textMuted,
              ),
            ),
    );
  }
}
