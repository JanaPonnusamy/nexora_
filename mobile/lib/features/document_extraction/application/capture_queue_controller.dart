import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_entry.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';

/// Outcome of a queue action, so the screen can say something specific rather
/// than a generic "something went wrong".
class QueueActionResult {
  const QueueActionResult({required this.message, this.ok = true});

  const QueueActionResult.failed(String message)
      : this(message: message, ok: false);

  final String message;
  final bool ok;
}

final captureQueueControllerProvider =
    Provider<CaptureQueueController>(CaptureQueueController.new);

/// The verbs of the capture queue: retry, delete, refresh.
///
/// Kept out of the screen so each action's semantics — especially delete,
/// which spans the device and the server — are testable without a widget tree.
class CaptureQueueController {
  CaptureQueueController(this._ref);

  final Ref _ref;
  final _log = AppLogger.of('CaptureQueue');

  CaptureQueueRepository get _queue =>
      _ref.read(captureQueueRepositoryProvider);

  /// Clears the backoff and attempt count, then tries immediately.
  Future<QueueActionResult> retryUpload(CaptureQueueEntry entry) async {
    await _queue.retryNow(entry.batchId);
    final report = await _ref.read(captureUploaderProvider).drain();

    if (report.skippedOffline) {
      // Not a failure: the job is queued and will go on reconnect. Saying
      // "failed" here would push the user into retrying by hand forever.
      return const QueueActionResult(
        message: 'Still offline — it will upload when you reconnect.',
      );
    }
    if (report.failed > 0 && report.uploaded == 0) {
      return const QueueActionResult.failed('Upload failed again.');
    }
    return const QueueActionResult(message: 'Uploaded.');
  }

  /// Re-runs the server pipeline for a document that uploaded but failed to
  /// extract.
  Future<QueueActionResult> retryPipeline(CaptureQueueEntry entry) async {
    final job = await _queue.byId(entry.batchId);
    if (job == null) {
      return const QueueActionResult.failed('That document is no longer here.');
    }
    try {
      final ok = await _ref.read(captureUploaderProvider).retryPipeline(job);
      return ok
          ? const QueueActionResult(message: 'Ready to review.')
          : const QueueActionResult.failed(
              'The server could not process it this time either.',
            );
    } on ApiException catch (e) {
      return QueueActionResult.failed(e.message);
    }
  }

  /// Removes a document from the device and, when it got that far, the server.
  ///
  /// The server copy is deleted first: dropping the local row first and then
  /// failing would leave an import the user believes is gone and can no longer
  /// see. If the server refuses, the local copy stays so the delete can be
  /// retried rather than silently half-applied.
  Future<QueueActionResult> delete(CaptureQueueEntry entry) async {
    final importId = entry.importId;
    if (importId != null) {
      try {
        await _ref.read(documentExtractionApiProvider).deleteImport(importId);
      } on ApiException catch (e) {
        _log.warning('Server delete of import $importId failed: ${e.message}');
        return QueueActionResult.failed(
          e.isNetwork
              ? 'Cannot reach the server, so it was left in place. '
                  'Try again when you are online.'
              : 'The server refused to delete it: ${e.message}',
        );
      }
    }

    await _queue.remove(entry.batchId);
    return const QueueActionResult(message: 'Deleted.');
  }

  /// Pull-to-refresh: drain anything due, then ask about anything in flight.
  Future<void> refresh() =>
      _ref.read(captureSyncCoordinatorProvider).refreshNow();

  /// Frees disk for documents that are already exported, keeping their rows.
  Future<QueueActionResult> reclaimSpace() async {
    final removed = await _queue.pruneExportedImages();
    return QueueActionResult(
      message: removed == 0
          ? 'Nothing to clear yet.'
          : 'Cleared $removed page image${removed == 1 ? '' : 's'}.',
    );
  }
}

/// The queue as the screen wants it: newest first, already resolved to
/// stages, labels and available actions.
final captureQueueEntriesProvider = StreamProvider<List<CaptureQueueEntry>>(
  (ref) => ref.watch(captureQueueRepositoryProvider).watchAll().map(
        (jobs) => jobs.map(CaptureQueueEntry.from).toList(growable: false),
      ),
);
