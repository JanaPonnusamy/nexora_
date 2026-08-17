import 'dart:io';

import 'package:drift/drift.dart' show DatabaseConnection;
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

void main() {
  late AppDatabase db;
  late CaptureQueueRepository queue;
  late Directory tmp;

  setUp(() async {
    db = AppDatabase.withExecutor(
      DatabaseConnection(NativeDatabase.memory()),
    );
    queue = CaptureQueueRepository(db);
    tmp = await Directory.systemTemp.createTemp('capture_queue_test');
  });

  tearDown(() async {
    await db.close();
    if (tmp.existsSync()) await tmp.delete(recursive: true);
  });

  Future<CapturePageDraft> page(String name,
      {String content = 'jpeg-bytes'}) async {
    final file = File('${tmp.path}/$name');
    await file.writeAsString(content);
    return CapturePageDraft(
      filePath: file.path,
      byteSize: await file.length(),
    );
  }

  group('enqueue', () {
    test('stores a batch with its pages in order', () async {
      final id = await queue.enqueue(
        tenantId: 't-1',
        storeId: 's-1',
        pages: [await page('a.jpg'), await page('b.jpg'), await page('c.jpg')],
      );

      final job = await queue.byId(id);
      expect(job, isNotNull);
      expect(job!.batch.pageCount, 3);
      expect(job.batch.tenantId, 't-1');
      expect(job.status, DocumentStatus.pendingUpload);
      expect(job.pages.map((p) => p.pageNumber), [1, 2, 3]);
      expect(job.pages.map((p) => p.filePath.split('/').last), [
        'a.jpg',
        'b.jpg',
        'c.jpg',
      ]);
    });

    test('a freshly enqueued job is immediately due', () async {
      await queue.enqueue(tenantId: 't-1', pages: [await page('a.jpg')]);
      expect(await queue.due(), hasLength(1));
    });

    test('totalBytes sums the pages', () async {
      final id = await queue.enqueue(
        tenantId: 't-1',
        pages: [
          await page('a.jpg', content: '12345'),
          await page('b.jpg', content: '1234567890'),
        ],
      );
      final job = await queue.byId(id);
      expect(job!.totalBytes, 15);
    });
  });

  group('retry and backoff', () {
    test('a failure schedules the next attempt in the future', () async {
      final id = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('a.jpg')],
      );
      await queue.markUploading(id);
      await queue.markFailed(id, 'connection reset');

      final job = await queue.byId(id);
      expect(job!.batch.lastError, 'connection reset');
      expect(job.batch.nextAttemptAt, isNotNull);
      expect(job.batch.nextAttemptAt!.isAfter(DateTime.now()), isTrue);
    });

    test('a backed-off job is not due until its window opens', () async {
      final id = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('a.jpg')],
      );
      await queue.markUploading(id);
      await queue.markFailed(id, 'timeout');

      expect(await queue.due(), isEmpty);
      // Far enough ahead to clear even the longest backoff step.
      final later = DateTime.now().add(const Duration(hours: 2));
      expect(await queue.due(now: later), hasLength(1));
    });

    test('backoff lengthens with each attempt', () async {
      final id = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('a.jpg')],
      );

      Duration? previous;
      for (var attempt = 0; attempt < 3; attempt++) {
        await queue.markUploading(id);
        await queue.markFailed(id, 'boom');
        final job = await queue.byId(id);
        final wait = job!.batch.nextAttemptAt!.difference(DateTime.now());
        if (previous != null) {
          expect(wait, greaterThan(previous));
        }
        previous = wait;
      }
    });

    test('a job stops being due once attempts are exhausted', () async {
      // An endlessly retrying upload burns battery and hides a real fault.
      final id = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('a.jpg')],
      );
      for (var i = 0; i < CaptureQueueRepository.maxAttempts; i++) {
        await queue.markUploading(id);
        await queue.markFailed(id, 'boom');
      }

      final far = DateTime.now().add(const Duration(days: 1));
      expect(await queue.due(now: far), isEmpty);
    });

    test('retryNow revives an exhausted job', () async {
      final id = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('a.jpg')],
      );
      for (var i = 0; i < CaptureQueueRepository.maxAttempts; i++) {
        await queue.markUploading(id);
        await queue.markFailed(id, 'boom');
      }

      await queue.retryNow(id);

      expect(await queue.due(), hasLength(1));
      final job = await queue.byId(id);
      expect(job!.batch.attemptCount, 0);
      expect(job.batch.lastError, isNull);
    });
  });

  group('upload lifecycle', () {
    test('markUploaded records the server import id and clears the queue',
        () async {
      final id = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('a.jpg')],
      );
      await queue.markUploaded(id, 4242);

      final job = await queue.byId(id);
      expect(job!.batch.importId, 4242);
      expect(job.status, DocumentStatus.uploaded);
      // No longer pending, so a later drain will not re-send it.
      expect(await queue.due(), isEmpty);
    });

    test('syncStatus mirrors the server pipeline state', () async {
      final id = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('a.jpg')],
      );
      await queue.markUploaded(id, 1);
      await queue.syncStatus(id, DocumentStatus.reviewPending);

      final job = await queue.byId(id);
      expect(job!.status, DocumentStatus.reviewPending);
      expect(job.status.needsReview, isTrue);
    });
  });

  group('disk hygiene', () {
    test('removing a job deletes its page files', () async {
      final draft = await page('a.jpg');
      final id = await queue.enqueue(tenantId: 't-1', pages: [draft]);
      expect(File(draft.filePath).existsSync(), isTrue);

      await queue.remove(id);

      // Page images live outside the database and would otherwise accumulate
      // until the user reinstalls.
      expect(File(draft.filePath).existsSync(), isFalse);
      expect(await queue.byId(id), isNull);
    });

    test('pruning exported batches frees images but keeps the history row',
        () async {
      final draft = await page('a.jpg');
      final id = await queue.enqueue(tenantId: 't-1', pages: [draft]);
      await queue.markUploaded(id, 7);
      await queue.markExported(id);

      final removed = await queue.pruneExportedImages();

      expect(removed, 1);
      expect(File(draft.filePath).existsSync(), isFalse);
      final job = await queue.byId(id);
      expect(job, isNotNull, reason: 'history must survive image pruning');
      expect(job!.pages, isEmpty);
    });

    test('a missing file does not break removal', () async {
      final draft = await page('a.jpg');
      final id = await queue.enqueue(tenantId: 't-1', pages: [draft]);
      await File(draft.filePath).delete();

      await queue.remove(id);
      expect(await queue.byId(id), isNull);
    });
  });

  group('ordering', () {
    test('due() returns oldest captures first', () async {
      final older = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('old.jpg')],
        capturedAt: DateTime.now().subtract(const Duration(hours: 3)),
      );
      final newer = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('new.jpg')],
        capturedAt: DateTime.now(),
      );

      final due = await queue.due();
      expect(due.map((j) => j.batch.id), [older, newer]);
    });

    test('all() lists newest first for the queue UI', () async {
      final older = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('old.jpg')],
        capturedAt: DateTime.now().subtract(const Duration(hours: 3)),
      );
      final newer = await queue.enqueue(
        tenantId: 't-1',
        pages: [await page('new.jpg')],
        capturedAt: DateTime.now(),
      );

      final all = await queue.all();
      expect(all.map((j) => j.batch.id), [newer, older]);
    });
  });
}
