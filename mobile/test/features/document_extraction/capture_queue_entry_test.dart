import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_entry.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

/// The queue screen's whole job is telling the truth about where a document
/// got to, so the mapping from a stored row to a stage, a sentence and a set of
/// buttons is the part worth pinning down.
void main() {
  final now = DateTime(2026, 8, 16, 12, 0);

  CaptureJob job({
    DocumentStatus status = DocumentStatus.pendingUpload,
    int? importId,
    int attemptCount = 0,
    String? lastError,
    DateTime? nextAttemptAt,
    int pageCount = 2,
    List<String?> qualityNotes = const [null, null],
  }) {
    return CaptureJob(
      batch: CaptureBatch(
        id: 7,
        importId: importId,
        tenantId: 't-1',
        status: status.wire,
        pageCount: pageCount,
        attemptCount: attemptCount,
        lastError: lastError,
        nextAttemptAt: nextAttemptAt,
        capturedAt: now.subtract(const Duration(minutes: 5)),
        updatedAt: now,
        isExported: false,
      ),
      pages: [
        for (var i = 0; i < qualityNotes.length; i++)
          CapturePage(
            id: i + 1,
            batchId: 7,
            filePath: '/tmp/page_${i + 1}.jpg',
            pageNumber: i + 1,
            byteSize: 500 * 1024,
            qualityNote: qualityNotes[i],
            createdAt: now,
          ),
      ],
    );
  }

  CaptureQueueEntry entryOf(CaptureJob j) =>
      CaptureQueueEntry.from(j, now: now);

  group('waiting to upload', () {
    test('a fresh capture is simply waiting', () {
      final entry = entryOf(job());

      expect(entry.stage, QueueStage.waiting);
      expect(entry.tone, QueueTone.neutral);
      expect(entry.statusLabel, 'Waiting to upload');
      expect(entry.actions, contains(QueueAction.retryUpload));
      expect(entry.needsUser, isFalse);
      expect(entry.isBusy, isFalse);
    });

    test('a scheduled retry says when, not just that it failed', () {
      final entry = entryOf(
        job(
          attemptCount: 2,
          lastError: 'Cannot reach the server.',
          nextAttemptAt: now.add(const Duration(minutes: 9, seconds: 30)),
        ),
      );

      expect(entry.stage, QueueStage.retrying);
      expect(entry.tone, QueueTone.warning);
      expect(entry.detail, 'Cannot reach the server. Next attempt in 9 min.');
    });

    test('a backoff that has already elapsed is due, not retrying', () {
      final entry = entryOf(
        job(
          attemptCount: 1,
          nextAttemptAt: now.subtract(const Duration(seconds: 1)),
        ),
      );

      expect(entry.stage, QueueStage.waiting);
    });

    test('an exhausted job stops and says so', () {
      final entry = entryOf(
        job(
          attemptCount: CaptureQueueRepository.maxAttempts,
          lastError: 'The server rejected the file.',
        ),
      );

      expect(entry.stage, QueueStage.stopped);
      expect(entry.tone, QueueTone.danger);
      expect(entry.needsUser, isTrue);
      expect(entry.detail, contains('Stopped after 6 attempts'));
      expect(entry.detail, contains('The server rejected the file.'));
      // A manual retry is the only thing that moves it.
      expect(entry.can(QueueAction.retryUpload), isTrue);
    });
  });

  group('server pipeline', () {
    test(
        'every in-flight status reads as processing and shows no buttons '
        'but delete', () {
      for (final status in [
        DocumentStatus.uploaded,
        DocumentStatus.ocrRunning,
        DocumentStatus.extracted,
      ]) {
        final entry = entryOf(job(status: status, importId: 42));

        expect(entry.stage, QueueStage.processing, reason: status.name);
        expect(entry.isBusy, isTrue, reason: status.name);
        expect(entry.actions, {QueueAction.delete}, reason: status.name);
      }
    });

    test('ready to review offers review', () {
      final entry = entryOf(
        job(status: DocumentStatus.reviewPending, importId: 42),
      );

      expect(entry.stage, QueueStage.readyToReview);
      expect(entry.tone, QueueTone.accent);
      expect(entry.needsUser, isTrue);
      expect(entry.can(QueueAction.review), isTrue);
    });

    test('a pipeline failure offers a pipeline retry, not a re-upload', () {
      final entry = entryOf(
        job(
          status: DocumentStatus.failed,
          importId: 42,
          lastError: 'OCR timed out.',
        ),
      );

      expect(entry.stage, QueueStage.failed);
      expect(entry.can(QueueAction.retryPipeline), isTrue);
      // Re-uploading pages the server already has would be wasted bandwidth.
      expect(entry.can(QueueAction.retryUpload), isFalse);
      expect(entry.detail, 'OCR timed out.');
    });

    test('saved is committed but not finished — it still owes an export', () {
      final entry = entryOf(job(status: DocumentStatus.saved, importId: 42));

      expect(entry.stage, QueueStage.saved);
      expect(entry.tone, QueueTone.accent);
      expect(entry.can(QueueAction.export), isTrue);
      expect(entry.detail, 'Ready to export into a workbook.');
    });

    test('exported is the end of the road, and still re-shareable', () {
      final entry = entryOf(job(status: DocumentStatus.exported, importId: 42));

      expect(entry.stage, QueueStage.exported);
      expect(entry.tone, QueueTone.success);
      expect(entry.can(QueueAction.export), isTrue);
      expect(entry.needsUser, isFalse);
    });

    test('EXPORTED is not mistaken for a document still being worked on', () {
      // It is a status the server sets on every export. Falling back to
      // UPLOADED would leave the poller chasing a finished document forever.
      final status = DocumentStatus.fromWire('EXPORTED');

      expect(status, DocumentStatus.exported);
      expect(status.isProcessing, isFalse);
      expect(status.isTerminal, isTrue);
    });
  });

  group('presentation', () {
    test('every stage can be deleted', () {
      for (final status in DocumentStatus.values) {
        expect(
          entryOf(job(status: status, importId: 1)).can(QueueAction.delete),
          isTrue,
          reason: status.name,
        );
      }
    });

    test('the title carries the server id once there is one', () {
      expect(entryOf(job()).title, '2 pages');
      expect(entryOf(job(importId: 91)).title, '2 pages · #91');
      expect(entryOf(job(pageCount: 1)).title, '1 page');
    });

    test(
        'pages flagged at capture are counted, so a bad extraction has an '
        'explanation', () {
      final entry = entryOf(
        job(qualityNotes: ['reject: Blurry', null, 'warn: Glare']),
      );

      expect(entry.flaggedPages, 2);
    });

    test('the first page is the thumbnail', () {
      expect(entryOf(job()).thumbnailPath, '/tmp/page_1.jpg');
    });

    test('a document whose images were reclaimed has no thumbnail', () {
      final entry = entryOf(job(qualityNotes: const []));

      expect(entry.thumbnailPath, isNull);
      expect(entry.totalBytes, 0);
    });

    test('size is human-readable at every scale', () {
      // Pages are 500 KiB each in this fixture.
      expect(entryOf(job(qualityNotes: const [null])).sizeLabel, '500 KB');
      expect(entryOf(job()).sizeLabel, '1000 KB');
      expect(
        entryOf(job(qualityNotes: const [null, null, null])).sizeLabel,
        '1.5 MB',
      );
      expect(entryOf(job(qualityNotes: const [])).sizeLabel, '0 B');
    });
  });
}
