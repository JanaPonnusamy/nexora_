import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:drift/drift.dart' show DatabaseConnection;
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_controller.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_entry.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_storage.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_uploader.dart';
import 'package:nexora_mobile/features/document_extraction/data/document_extraction_api.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

/// Records what the queue asked the server to do, and can be told to refuse.
class FakeExtractionApi extends DocumentExtractionApi {
  // The superclass needs a Dio; every method that would use one is overridden,
  // so no request escapes.
  FakeExtractionApi({this.deleteError, this.stageError}) : super(_unusedDio);

  final ApiException? deleteError;
  final ApiException? stageError;

  final deleted = <int>[];
  final stagesRun = <DocumentStage>[];
  final uploaded = <List<File>>[];

  @override
  Future<void> deleteImport(int importId) async {
    if (deleteError != null) throw deleteError!;
    deleted.add(importId);
  }

  @override
  Future<void> runStage(int importId, DocumentStage stage,
      {String? actor}) async {
    if (stageError != null) throw stageError!;
    stagesRun.add(stage);
  }

  @override
  Future<List<int>> upload({
    required List<File> files,
    required String tenantId,
    String? storeId,
    String? actor,
    bool groupAsSingleInvoice = true,
    void Function(int, int)? onProgress,
    CancelToken? cancelToken,
  }) async {
    uploaded.add(files);
    return [900 + uploaded.length];
  }
}

final _unusedDio = Dio();

class FakeConnectivity extends ConnectivityService {
  FakeConnectivity({this.online = true});

  bool online;

  @override
  Future<NetworkStatus> check() async =>
      online ? NetworkStatus.online : NetworkStatus.offline;

  @override
  Future<void> start() async {}
}

void main() {
  late AppDatabase db;
  late Directory tmp;
  late FakeExtractionApi api;
  late FakeConnectivity connectivity;

  setUp(() async {
    db = AppDatabase.withExecutor(DatabaseConnection(NativeDatabase.memory()));
    tmp = await Directory.systemTemp.createTemp('capture_queue_ctl_test');
    api = FakeExtractionApi();
    connectivity = FakeConnectivity();
  });

  tearDown(() async {
    await db.close();
    if (tmp.existsSync()) await tmp.delete(recursive: true);
  });

  ProviderContainer container() {
    final c = ProviderContainer(
      overrides: [
        appDatabaseProvider.overrideWithValue(db),
        documentExtractionApiProvider.overrideWithValue(api),
        connectivityServiceProvider.overrideWithValue(connectivity),
        // The queue rebases page paths through storage, and the real one asks
        // path_provider for the documents directory — a platform channel that
        // does not exist under `flutter test`.
        captureStorageProvider.overrideWithValue(CaptureStorage(root: tmp)),
      ],
    );
    addTearDown(c.dispose);
    return c;
  }

  Future<File> pageFile(String name) async {
    final file = File('${tmp.path}/$name');
    await file.writeAsBytes(Uint8List.fromList([1, 2, 3, 4]));
    return file;
  }

  /// Queues a batch and returns the entry the screen would render for it.
  Future<CaptureQueueEntry> queued(
    ProviderContainer c, {
    int pages = 1,
    int? importId,
    DocumentStatus? status,
  }) async {
    final repo = c.read(captureQueueRepositoryProvider);
    final id = await repo.enqueue(
      tenantId: 't-1',
      pages: [
        for (var i = 0; i < pages; i++)
          CapturePageDraft(
            filePath: (await pageFile(
                    'p$i-${DateTime.now().microsecondsSinceEpoch}.jpg'))
                .path,
            byteSize: 4,
          ),
      ],
    );
    if (importId != null) await repo.markUploaded(id, importId);
    if (status != null) await repo.syncStatus(id, status);
    return CaptureQueueEntry.from((await repo.byId(id))!);
  }

  group('delete', () {
    test('a document that never uploaded is removed with its files', () async {
      final c = container();
      final entry = await queued(c, pages: 2);
      final files =
          (await c.read(captureQueueRepositoryProvider).byId(entry.batchId))!
              .files;

      final result = await c.read(captureQueueControllerProvider).delete(entry);

      expect(result.ok, isTrue);
      expect(api.deleted, isEmpty, reason: 'never reached the server');
      expect(
        await c.read(captureQueueRepositoryProvider).byId(entry.batchId),
        isNull,
      );
      for (final f in files) {
        expect(f.existsSync(), isFalse);
      }
    });

    test('an uploaded document is deleted on the server too', () async {
      final c = container();
      final entry = await queued(c, importId: 55);

      final result = await c.read(captureQueueControllerProvider).delete(entry);

      expect(result.ok, isTrue);
      expect(api.deleted, [55]);
      expect(
        await c.read(captureQueueRepositoryProvider).byId(entry.batchId),
        isNull,
      );
    });

    test('a server refusal leaves the local copy alone so it can be retried',
        () async {
      api = FakeExtractionApi(
        deleteError: const ApiException(
          message: 'Cannot reach the server.',
          isNetwork: true,
        ),
      );
      final c = container();
      final entry = await queued(c, importId: 55);

      final result = await c.read(captureQueueControllerProvider).delete(entry);

      expect(result.ok, isFalse);
      expect(result.message, contains('left in place'));
      // Still there — a half-applied delete would strand an import the user
      // believes is gone.
      expect(
        await c.read(captureQueueRepositoryProvider).byId(entry.batchId),
        isNotNull,
      );
    });
  });

  group('retryUpload', () {
    test('clears the backoff and uploads', () async {
      final c = container();
      final repo = c.read(captureQueueRepositoryProvider);
      final entry = await queued(c);
      await repo.markFailed(entry.batchId, 'nope');
      await repo.markFailed(entry.batchId, 'nope again');

      final result =
          await c.read(captureQueueControllerProvider).retryUpload(entry);

      expect(result.ok, isTrue);
      final job = await repo.byId(entry.batchId);
      expect(job!.status, DocumentStatus.reviewPending);
      expect(api.uploaded, hasLength(1));
    });

    test('offline is reported as queued, not as a failure', () async {
      connectivity.online = false;
      final c = container();
      final entry = await queued(c);

      final result =
          await c.read(captureQueueControllerProvider).retryUpload(entry);

      // Calling this a failure would train the user to keep tapping retry.
      expect(result.ok, isTrue);
      expect(result.message, contains('offline'));
      expect(api.uploaded, isEmpty);
    });

    test('an exhausted job becomes eligible again', () async {
      final c = container();
      final repo = c.read(captureQueueRepositoryProvider);
      final entry = await queued(c);
      // The real drain bumps the attempt count on the way in and records the
      // failure on the way out; only the pair exhausts a job.
      for (var i = 0; i < CaptureQueueRepository.maxAttempts; i++) {
        await repo.markUploading(entry.batchId);
        await repo.markFailed(entry.batchId, 'nope');
      }
      expect(
        CaptureQueueEntry.from((await repo.byId(entry.batchId))!).stage,
        QueueStage.stopped,
      );

      await c.read(captureQueueControllerProvider).retryUpload(entry);

      expect((await repo.byId(entry.batchId))!.batch.attemptCount, 1);
    });
  });

  group('retryPipeline', () {
    test('re-runs the whole pipeline for an uploaded document', () async {
      final c = container();
      final entry = await queued(
        c,
        importId: 55,
        status: DocumentStatus.failed,
      );

      final result =
          await c.read(captureQueueControllerProvider).retryPipeline(entry);

      expect(result.ok, isTrue);
      expect(api.stagesRun, CaptureUploader.pipeline);
      expect(
        (await c.read(captureQueueRepositoryProvider).byId(entry.batchId))!
            .status,
        DocumentStatus.reviewPending,
      );
    });

    test('a stage that fails again is reported, not swallowed', () async {
      api = FakeExtractionApi(
        stageError: const ApiException(message: 'OCR timed out.'),
      );
      final c = container();
      final entry = await queued(
        c,
        importId: 55,
        status: DocumentStatus.failed,
      );

      final result =
          await c.read(captureQueueControllerProvider).retryPipeline(entry);

      expect(result.ok, isFalse);
      expect(
        (await c.read(captureQueueRepositoryProvider).byId(entry.batchId))!
            .status,
        DocumentStatus.failed,
      );
    });
  });

  group('reclaimSpace', () {
    test('drops page images of exported documents only', () async {
      final c = container();
      final repo = c.read(captureQueueRepositoryProvider);
      final exported = await queued(c, pages: 2, importId: 1);
      final kept = await queued(c, pages: 1);
      await repo.markExported(exported.batchId);

      final result =
          await c.read(captureQueueControllerProvider).reclaimSpace();

      expect(result.message, contains('2 page images'));
      // The row survives so history still lists it.
      expect(await repo.byId(exported.batchId), isNotNull);
      expect((await repo.byId(exported.batchId))!.pages, isEmpty);
      expect((await repo.byId(kept.batchId))!.pages, hasLength(1));
    });
  });

  group('a page missing from storage', () {
    /// Deleting the image is how the OS reclaiming storage looks to the queue:
    /// the row is still pending, the file it points at is not there.
    Future<CaptureQueueEntry> orphaned(ProviderContainer c) async {
      final entry = await queued(c);
      final repo = c.read(captureQueueRepositoryProvider);
      final job = await repo.byId(entry.batchId);
      await File(job!.pages.first.filePath).delete();
      return entry;
    }

    test('counts the attempt rather than failing for free', () async {
      // An uncounted attempt is one the give-up cap never sees: the batch stays
      // under maxAttempts for ever and comes back due on every drain.
      final c = container();
      final entry = await orphaned(c);
      final repo = c.read(captureQueueRepositoryProvider);

      final report = await c.read(captureUploaderProvider).drain();

      expect(report.failed, 1);
      final batch = (await repo.byId(entry.batchId))!.batch;
      expect(batch.attemptCount, 1);
      expect(batch.lastError, contains('missing from storage'));
      // Nothing was sent — the point of the check is to not upload a
      // half-present invoice.
      expect(api.uploaded, isEmpty);
    });

    test('stops, and says so, once the attempts are spent', () async {
      final c = container();
      final entry = await orphaned(c);
      final repo = c.read(captureQueueRepositoryProvider);
      for (var i = 0; i < CaptureQueueRepository.maxAttempts - 1; i++) {
        await repo.markUploading(entry.batchId);
      }

      await c.read(captureUploaderProvider).drain();

      final job = await repo.byId(entry.batchId);
      final settled = CaptureQueueEntry.from(job!);
      expect(settled.stage, QueueStage.stopped);
      expect(settled.detail, contains('missing from storage'));
      // Not due again at any point in the future, so the user's retry button is
      // now the only thing that moves it.
      expect(
        await repo.due(now: DateTime.now().add(const Duration(days: 1))),
        isEmpty,
      );
    });
  });
}
