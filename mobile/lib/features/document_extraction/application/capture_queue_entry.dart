import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

/// What a queued document is doing, in the terms the queue screen shows.
///
/// This is deliberately coarser than [DocumentStatus]: the server's pipeline
/// states all read as "working on it" to someone standing at a counter, while
/// the two states the server has no idea about — *backing off* and *given up*
/// — are exactly the ones a user has to be able to act on.
enum QueueStage {
  /// On the device, due for an upload attempt.
  waiting,

  /// Failed an attempt; a retry is scheduled.
  retrying,

  /// Out of automatic attempts. Only a manual retry moves this.
  stopped,

  /// Uploaded; the server pipeline is running.
  processing,

  /// Extracted and waiting for a human.
  readyToReview,

  /// Reviewed and committed.
  saved,

  /// Written into a workbook. The end of the road for a captured document —
  /// and the point at which its page images can be reclaimed.
  exported,

  /// The server pipeline failed.
  failed,
}

/// Colour role, resolved to a palette entry by the widget layer so this stays
/// free of Flutter.
enum QueueTone { neutral, info, accent, success, warning, danger }

/// Something the user can do to a queued document.
enum QueueAction {
  /// Clear the backoff and upload now.
  retryUpload,

  /// Re-run the server pipeline for an already-uploaded document.
  retryPipeline,

  review,

  /// Build a workbook for this document and hand it to the share sheet.
  /// Offered again after an export: a workbook that went to the wrong person,
  /// or to a chat that has since been cleared, has to be re-sendable.
  export,

  delete,
}

/// One row of the capture queue, derived entirely from a [CaptureJob].
///
/// Pure and time-explicit so the backoff and give-up states can be tested
/// without waiting for real clocks.
class CaptureQueueEntry {
  const CaptureQueueEntry({
    required this.batchId,
    required this.importId,
    required this.pageCount,
    required this.capturedAt,
    required this.stage,
    required this.statusLabel,
    required this.actions,
    this.detail,
    this.thumbnailPath,
    this.flaggedPages = 0,
    this.totalBytes = 0,
  });

  final int batchId;
  final int? importId;
  final int pageCount;
  final DateTime capturedAt;
  final QueueStage stage;

  /// Short state, for the badge.
  final String statusLabel;

  /// The sentence under the title: why it is stuck, or when it retries.
  final String? detail;

  final Set<QueueAction> actions;
  final String? thumbnailPath;
  final int flaggedPages;
  final int totalBytes;

  factory CaptureQueueEntry.from(CaptureJob job, {DateTime? now}) {
    final at = now ?? DateTime.now();
    final batch = job.batch;
    final (stage, label, detail) = _resolve(job, at);

    return CaptureQueueEntry(
      batchId: batch.id,
      importId: batch.importId,
      pageCount: batch.pageCount,
      capturedAt: batch.capturedAt,
      stage: stage,
      statusLabel: label,
      detail: detail,
      actions: _actionsFor(stage),
      // The first page is the one with the invoice header on it, so it is the
      // page worth showing as the thumbnail.
      thumbnailPath: job.pages.isEmpty ? null : job.pages.first.filePath,
      flaggedPages: job.pages.where((p) => p.qualityNote != null).length,
      totalBytes: job.totalBytes,
    );
  }

  static (QueueStage, String, String?) _resolve(CaptureJob job, DateTime now) {
    final batch = job.batch;
    final status = job.status;

    if (status == DocumentStatus.pendingUpload) {
      if (batch.attemptCount >= CaptureQueueRepository.maxAttempts) {
        // Stopping is deliberate — an endlessly retrying job burns battery and
        // hides a real problem. Say so plainly rather than showing a spinner
        // that will never resolve.
        return (
          QueueStage.stopped,
          'Upload stopped',
          batch.lastError == null
              ? 'Stopped after ${batch.attemptCount} attempts.'
              : 'Stopped after ${batch.attemptCount} attempts. '
                  '${batch.lastError}',
        );
      }

      final next = batch.nextAttemptAt;
      if (next != null && next.isAfter(now)) {
        final wait = _humanise(next.difference(now));
        return (
          QueueStage.retrying,
          'Retrying',
          batch.lastError == null
              ? 'Next attempt in $wait.'
              : '${batch.lastError} Next attempt in $wait.',
        );
      }

      return (
        QueueStage.waiting,
        'Waiting to upload',
        batch.lastError ?? 'Uploads as soon as there is a connection.',
      );
    }

    if (status.isProcessing) {
      return (QueueStage.processing, status.label, 'Reading the document.');
    }

    return switch (status) {
      DocumentStatus.reviewPending => (
          QueueStage.readyToReview,
          'Ready to review',
          'Check the extracted details before exporting.',
        ),
      DocumentStatus.saved => (
          QueueStage.saved,
          'Saved',
          'Ready to export into a workbook.',
        ),
      DocumentStatus.exported => (
          QueueStage.exported,
          'Exported',
          'In a workbook. Its page images can be cleared to free up space.',
        ),
      _ => (
          QueueStage.failed,
          'Failed',
          batch.lastError ?? 'The server could not process this document.',
        ),
    };
  }

  static Set<QueueAction> _actionsFor(QueueStage stage) => switch (stage) {
        // Deleting is always available: the device is the only thing standing
        // between a bad capture and the user's storage filling up.
        QueueStage.waiting || QueueStage.retrying || QueueStage.stopped => {
            QueueAction.retryUpload,
            QueueAction.delete
          },
        QueueStage.processing => {QueueAction.delete},
        QueueStage.readyToReview => {QueueAction.review, QueueAction.delete},
        QueueStage.saved => {
            QueueAction.export,
            QueueAction.review,
            QueueAction.delete,
          },
        QueueStage.exported => {
            QueueAction.export,
            QueueAction.review,
            QueueAction.delete,
          },
        QueueStage.failed => {QueueAction.retryPipeline, QueueAction.delete},
      };

  QueueTone get tone => switch (stage) {
        QueueStage.waiting => QueueTone.neutral,
        QueueStage.retrying => QueueTone.warning,
        QueueStage.stopped => QueueTone.danger,
        QueueStage.processing => QueueTone.info,
        QueueStage.readyToReview => QueueTone.accent,
        QueueStage.saved => QueueTone.accent,
        QueueStage.exported => QueueTone.success,
        QueueStage.failed => QueueTone.danger,
      };

  /// True while the server is working — the card shows an indeterminate bar.
  bool get isBusy => stage == QueueStage.processing;

  /// True when only the user can move this along.
  bool get needsUser =>
      stage == QueueStage.stopped ||
      stage == QueueStage.failed ||
      stage == QueueStage.readyToReview;

  bool can(QueueAction action) => actions.contains(action);

  String get title => '$pageCount page${pageCount == 1 ? '' : 's'}'
      '${importId == null ? '' : ' · #$importId'}';

  String get sizeLabel => totalBytes < 1024
      ? '$totalBytes B'
      : totalBytes < 1024 * 1024
          ? '${(totalBytes / 1024).round()} KB'
          : '${(totalBytes / (1024 * 1024)).toStringAsFixed(1)} MB';

  static String _humanise(Duration d) {
    if (d.inMinutes < 1) return '${d.inSeconds.clamp(1, 59)} sec';
    if (d.inMinutes < 60) return '${d.inMinutes} min';
    return '${d.inHours} h';
  }
}
