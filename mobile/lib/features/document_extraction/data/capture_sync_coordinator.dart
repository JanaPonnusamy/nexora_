import 'dart:async';

import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_uploader.dart';

/// Keeps the capture queue moving without anyone looking at it.
///
/// Without this, a capture taken in a basement stockroom uploads only if the
/// user happens to open the app again while online — which is precisely the
/// user who walked away believing the job was done. Two triggers:
///
/// * **Reconnect.** The OS reports a network again → drain.
/// * **In-flight polling.** A document uploaded before the app was killed may
///   still be mid-pipeline on the server. Poll those, and only those, so a
///   quiet queue costs nothing.
class CaptureSyncCoordinator {
  CaptureSyncCoordinator({
    required CaptureQueueRepository queue,
    required CaptureUploader uploader,
    required ConnectivityService connectivity,
  })  : _queue = queue,
        _uploader = uploader,
        _connectivity = connectivity;

  final CaptureQueueRepository _queue;
  final CaptureUploader _uploader;
  final ConnectivityService _connectivity;
  final _log = AppLogger.of('CaptureSync');

  /// How often to ask the server about a document it is still working on.
  /// The pipeline stages run in seconds, so this is a safety net for a killed
  /// app rather than a progress bar — it does not need to be tight.
  static const Duration pollInterval = Duration(seconds: 8);

  StreamSubscription<NetworkStatus>? _connSub;
  Timer? _poll;
  bool _started = false;

  /// Idempotent — the app calls this whenever a session becomes ready.
  Future<void> start() async {
    if (_started) return;
    _started = true;

    await _connectivity.start();
    _connSub = _connectivity.statusStream.listen((status) {
      if (status.isOnline) {
        _log.info('Network returned — draining the capture queue');
        unawaited(_drainQuietly());
      }
    });

    // Anything left over from the last run: a capture queued offline, or a
    // document that was mid-pipeline when the app died.
    unawaited(_drainQuietly());
    await _reschedulePoll();
  }

  /// Drains and then refreshes in-flight statuses. Backs the queue screen's
  /// pull-to-refresh, where the user is explicitly asking for progress.
  Future<void> refreshNow() async {
    await _drainQuietly();
    await _pollInFlight();
  }

  Future<void> _drainQuietly() async {
    try {
      final report = await _uploader.drain();
      if (report.attempted > 0) {
        _log.info(
          'Drain: ${report.uploaded} uploaded, ${report.failed} failed',
        );
      }
    } on Object catch (e) {
      // The queue has its own backoff; a drain that blew up must not take the
      // coordinator's subscription down with it.
      _log.warning('Drain failed: $e');
    }
    await _reschedulePoll();
  }

  /// Asks the server about every document it is still working on.
  Future<void> _pollInFlight() async {
    final jobs = await _inFlight();
    if (jobs.isEmpty) {
      _stopPoll();
      return;
    }
    for (final job in jobs) {
      await _uploader.refreshStatus(job);
    }
    await _reschedulePoll();
  }

  Future<List<CaptureJob>> _inFlight() async {
    final all = await _queue.all();
    return all
        .where((j) => j.batch.importId != null && j.status.isProcessing)
        .toList(growable: false);
  }

  /// Runs the poll timer only while there is something to poll.
  Future<void> _reschedulePoll() async {
    final hasWork = (await _inFlight()).isNotEmpty;
    if (!hasWork) {
      _stopPoll();
      return;
    }
    if (_poll != null) return;
    _poll = Timer.periodic(pollInterval, (_) => unawaited(_pollInFlight()));
  }

  void _stopPoll() {
    _poll?.cancel();
    _poll = null;
  }

  Future<void> dispose() async {
    _stopPoll();
    await _connSub?.cancel();
    _connSub = null;
    _started = false;
  }
}
