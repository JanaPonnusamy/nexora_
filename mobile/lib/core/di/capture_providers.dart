import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_processor.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_storage.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_sync_coordinator.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_uploader.dart';
import 'package:nexora_mobile/features/document_extraction/data/document_extraction_api.dart';

/// Phase 2 — document capture and the OCR pipeline client.
///
/// Split out of `providers.dart` because the capture graph is self-contained:
/// a screen that only photographs pages should not pull in the sync engine.

/// Typed client for `/api/document-extraction/*`.
final documentExtractionApiProvider = Provider<DocumentExtractionApi>(
  (ref) => DocumentExtractionApi(ref.watch(dioProvider)),
);

/// Durable queue of captured-but-not-yet-uploaded documents.
final captureQueueRepositoryProvider = Provider<CaptureQueueRepository>(
  (ref) => CaptureQueueRepository(ref.watch(appDatabaseProvider)),
);

/// Page images on disk, outside the database.
final captureStorageProvider = Provider<CaptureStorage>(
  (ref) => CaptureStorage(),
);

/// Decode / downscale / quality-gate pass, run in an isolate.
final captureProcessorProvider = Provider<CaptureProcessor>(
  (ref) => const CaptureProcessor(),
);

/// Drains the queue and walks each import through the server pipeline.
final captureUploaderProvider = Provider<CaptureUploader>(
  (ref) => CaptureUploader(
    queue: ref.watch(captureQueueRepositoryProvider),
    api: ref.watch(documentExtractionApiProvider),
    connectivity: ref.watch(connectivityServiceProvider),
  ),
);

/// Live view of the local queue, for the capture tab's status strip and the
/// queue screen.
final captureQueueStreamProvider = StreamProvider<List<CaptureJob>>(
  (ref) => ref.watch(captureQueueRepositoryProvider).watchAll(),
);

/// Drains on reconnect and polls documents the server is still working on.
/// Started by the app once a session is ready; see `app.dart`.
final captureSyncCoordinatorProvider = Provider<CaptureSyncCoordinator>((ref) {
  final coordinator = CaptureSyncCoordinator(
    queue: ref.watch(captureQueueRepositoryProvider),
    uploader: ref.watch(captureUploaderProvider),
    connectivity: ref.watch(connectivityServiceProvider),
  );
  ref.onDispose(coordinator.dispose);
  return coordinator;
});
