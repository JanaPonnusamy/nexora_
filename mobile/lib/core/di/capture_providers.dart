import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/outbox/outbox_dispatcher.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_review_controller.dart';
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

/// Page images on disk, outside the database.
final captureStorageProvider = Provider<CaptureStorage>(
  (ref) => CaptureStorage(),
);

/// Durable queue of captured-but-not-yet-uploaded documents.
final captureQueueRepositoryProvider = Provider<CaptureQueueRepository>(
  (ref) => CaptureQueueRepository(
    ref.watch(appDatabaseProvider),
    ref.watch(captureStorageProvider),
  ),
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

/// Teaches the outbox how to send the review screen's four edits.
///
/// Registered here rather than in `core/` so the dispatcher stays ignorant of
/// features — the same shape as the sync engine's registered entity processors.
/// Reading this provider is what performs the registration, so the app reads it
/// once at startup.
final reviewOutboxHandlersProvider = Provider<void>((ref) {
  final dispatcher = ref.watch(outboxDispatcherProvider);
  final api = ref.watch(documentExtractionApiProvider);

  Map<String, dynamic> fieldsOf(Map<String, dynamic> payload) =>
      (payload['fields'] as Map?)?.cast<String, dynamic>() ?? const {};

  /// Registers [send], then re-runs validation.
  ///
  /// Re-validating is not optional, for the same reason an online edit does it
  /// (§3.12): `save` reads the *stored* `validation_status`, and nothing about
  /// a patch recomputes it. Without this an offline correction syncs and the
  /// user is still asked to override the error they fixed yesterday.
  void registerEdit(String kind, OutboxHandler send) {
    dispatcher.register(kind, (payload) async {
      await send(payload);
      try {
        await api.runStage(
          payload['importId'] as int,
          DocumentStage.validate,
          actor: payload['actor'] as String?,
        );
      } on ApiException {
        // The edit is on the server, which is the part that must not be lost.
        // Failing the entry here would re-send it and write a duplicate audit
        // row; stale findings are only a nuisance.
      }
    });
  }

  registerEdit(ReviewOutboxKinds.header, (payload) async {
    await api.patchHeader(
      payload['importId'] as int,
      fieldsOf(payload),
      actor: payload['actor'] as String?,
    );
  });

  registerEdit(ReviewOutboxKinds.item, (payload) async {
    await api.patchItem(
      payload['importId'] as int,
      payload['itemId'] as int,
      fieldsOf(payload),
      actor: payload['actor'] as String?,
    );
  });

  registerEdit(ReviewOutboxKinds.exclude, (payload) async {
    await api.excludeItem(
      payload['importId'] as int,
      payload['itemId'] as int,
      actor: payload['actor'] as String?,
    );
  });

  registerEdit(ReviewOutboxKinds.supplier, (payload) async {
    await api.assignSupplier(
      payload['importId'] as int,
      fieldsOf(payload),
      actor: payload['actor'] as String?,
    );
  });
});

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
