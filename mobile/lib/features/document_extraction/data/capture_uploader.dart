import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/data/document_extraction_api.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

/// Result of one drain pass.
class DrainReport {
  const DrainReport({
    this.uploaded = 0,
    this.failed = 0,
    this.skippedOffline = false,
  });

  final int uploaded;
  final int failed;
  final bool skippedOffline;

  int get attempted => uploaded + failed;
}

/// Drains the capture queue and runs each upload through the server pipeline.
///
/// The server exposes preprocess → ocr → extract → validate as separate
/// endpoints so a failure can be resumed from where it broke. This mirrors the
/// web console's `documentExtractionPipeline.ts`: run the stages in order so
/// the reviewer lands on a populated screen rather than an empty shell.
class CaptureUploader {
  CaptureUploader({
    required CaptureQueueRepository queue,
    required DocumentExtractionApi api,
    required ConnectivityService connectivity,
  })  : _queue = queue,
        _api = api,
        _connectivity = connectivity;

  final CaptureQueueRepository _queue;
  final DocumentExtractionApi _api;
  final ConnectivityService _connectivity;
  final _log = AppLogger.of('CaptureUploader');

  bool _draining = false;

  /// Stages run after a successful upload, in order.
  static const List<DocumentStage> pipeline = [
    DocumentStage.preprocess,
    DocumentStage.ocr,
    DocumentStage.extract,
    DocumentStage.validate,
  ];

  /// Uploads every due job. Safe to call often — concurrent calls collapse into
  /// the one already running, so a reconnect event plus a manual pull-to-refresh
  /// cannot upload the same batch twice.
  Future<DrainReport> drain({String? actor}) async {
    if (_draining) {
      _log.fine('Drain already in progress');
      return const DrainReport();
    }
    if (!await _connectivity.isOnline) {
      _log.info('Offline — leaving the capture queue untouched');
      return const DrainReport(skippedOffline: true);
    }

    _draining = true;
    var uploaded = 0;
    var failed = 0;
    try {
      final jobs = await _queue.due();
      _log.info('Draining ${jobs.length} capture job(s)');

      for (final job in jobs) {
        final ok = await _process(job, actor: actor);
        if (ok) {
          uploaded++;
        } else {
          failed++;
        }
      }
    } finally {
      _draining = false;
    }
    return DrainReport(uploaded: uploaded, failed: failed);
  }

  Future<bool> _process(CaptureJob job, {String? actor}) async {
    final batchId = job.batch.id;

    // Counted before anything below can fail. Reading the local files is part
    // of the attempt, and an attempt that is never recorded is one the backoff
    // and the give-up cap never see: the batch stays under `maxAttempts`, comes
    // back due on the next drain, and never reaches "Upload stopped" — the one
    // state that tells the user their pages are gone and asks them to act.
    await _queue.markUploading(batchId);

    // A file can vanish between capture and upload (OS cleanup, user clearing
    // storage). Failing loudly here beats sending a truncated invoice.
    for (final file in job.files) {
      if (!await file.exists()) {
        await _queue.markFailed(
            batchId, 'A captured page is missing from storage');
        return false;
      }
    }

    try {
      final importIds = await _api.upload(
        files: job.files,
        tenantId: job.batch.tenantId,
        storeId: job.batch.storeId,
        actor: actor,
      );

      if (importIds.isEmpty) {
        await _queue.markFailed(
            batchId, 'Server accepted the upload but returned no import');
        return false;
      }

      final importId = importIds.first;
      await _queue.markUploaded(batchId, importId);
      _log.info('Batch $batchId uploaded as import $importId');

      await _runPipeline(importId, batchId, actor: actor);
      return true;
    } on ApiException catch (e) {
      _log.warning('Batch $batchId upload failed: ${e.message}');
      await _queue.markFailed(batchId, e.message);
      return false;
    }
  }

  /// Advances an uploaded import through the pipeline.
  ///
  /// A stage failure is not a queue failure: the document is already safe on
  /// the server, so the local row is marked FAILED for the user to reprocess
  /// rather than re-uploading the images.
  Future<void> _runPipeline(
    int importId,
    int batchId, {
    String? actor,
  }) async {
    for (final stage in pipeline) {
      try {
        await _api.runStage(importId, stage, actor: actor);
      } on ApiException catch (e) {
        _log.warning(
          'Import $importId failed at ${stage.name}: ${e.message}',
        );
        await _queue.syncStatus(batchId, DocumentStatus.failed);
        return;
      }
    }
    await _queue.syncStatus(batchId, DocumentStatus.reviewPending);
  }

  /// Re-runs the server pipeline for a document that is already uploaded.
  ///
  /// Restarts from the first stage rather than resuming: only the *last*
  /// stage's failure reaches this side, so the device does not know where the
  /// server broke. Re-running preprocess is idempotent there, and the cost —
  /// one more OCR pass — is paid only on a retry the user asked for. Recording
  /// the failing stage locally is what would let this resume in place.
  ///
  /// Returns true if the document came out of the pipeline reviewable.
  Future<bool> retryPipeline(CaptureJob job, {String? actor}) async {
    final importId = job.batch.importId;
    if (importId == null) return false;

    await _queue.syncStatus(job.batch.id, DocumentStatus.uploaded);
    await _runPipeline(importId, job.batch.id, actor: actor);

    final refreshed = await _queue.byId(job.batch.id);
    return refreshed?.status == DocumentStatus.reviewPending;
  }

  /// Refreshes the local status of an already-uploaded batch from the server.
  /// Used by the queue screen while a document is still processing.
  Future<DocumentStatus?> refreshStatus(CaptureJob job) async {
    final importId = job.batch.importId;
    if (importId == null) return null;
    try {
      final summary = await _api.importSummary(importId);
      final status = DocumentStatus.fromWire(summary['status']?.toString());
      await _queue.syncStatus(job.batch.id, status);
      return status;
    } on ApiException catch (e) {
      _log.fine('Status refresh for import $importId failed: ${e.message}');
      return null;
    }
  }
}
