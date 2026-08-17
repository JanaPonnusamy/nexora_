import 'dart:io';

import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

/// A queued capture with its pages.
class CaptureJob {
  const CaptureJob({required this.batch, required this.pages});

  final CaptureBatch batch;
  final List<CapturePage> pages;

  DocumentStatus get status => DocumentStatus.fromWire(batch.status);

  List<File> get files =>
      pages.map((p) => File(p.filePath)).toList(growable: false);

  int get totalBytes => pages.fold(0, (sum, p) => sum + p.byteSize);
}

/// Durable store for captured-but-not-yet-uploaded documents.
///
/// A capture is written here before anything is sent, so an invoice
/// photographed in a basement stockroom survives the app being killed and
/// uploads when signal returns.
class CaptureQueueRepository {
  CaptureQueueRepository(this._db);

  final AppDatabase _db;

  /// Retry backoff, capped. Uploads are large and a store on a bad connection
  /// should not retry every few seconds.
  static const List<Duration> retryBackoff = [
    Duration(seconds: 30),
    Duration(minutes: 2),
    Duration(minutes: 10),
    Duration(minutes: 30),
  ];

  /// Give up after this many attempts and let the user retry by hand — an
  /// endlessly-retrying job burns battery and hides a real problem.
  static const int maxAttempts = 6;

  /// Records a new capture. Pages must already be written to disk.
  Future<int> enqueue({
    required String tenantId,
    String? storeId,
    required List<CapturePageDraft> pages,
    DateTime? capturedAt,
  }) async {
    return _db.transaction(() async {
      final batchId = await _db.into(_db.captureBatches).insert(
            CaptureBatchesCompanion.insert(
              tenantId: tenantId,
              storeId: Value(storeId),
              pageCount: Value(pages.length),
              capturedAt: capturedAt ?? DateTime.now(),
            ),
          );

      for (var i = 0; i < pages.length; i++) {
        final page = pages[i];
        await _db.into(_db.capturePages).insert(
              CapturePagesCompanion.insert(
                batchId: batchId,
                filePath: page.filePath,
                pageNumber: i + 1,
                byteSize: Value(page.byteSize),
                qualityNote: Value(page.qualityNote),
              ),
            );
      }
      return batchId;
    });
  }

  /// Jobs that are due for an upload attempt now, oldest first.
  Future<List<CaptureJob>> due({DateTime? now}) async {
    final at = now ?? DateTime.now();
    final batches = await (_db.select(_db.captureBatches)
          ..where((t) => t.status.equals(DocumentStatus.pendingUpload.wire))
          ..where((t) => t.attemptCount.isSmallerThanValue(maxAttempts))
          ..where(
            (t) =>
                t.nextAttemptAt.isNull() |
                t.nextAttemptAt.isSmallerOrEqualValue(at),
          )
          ..orderBy([(t) => OrderingTerm.asc(t.capturedAt)]))
        .get();

    return Future.wait(batches.map(_withPages));
  }

  /// Everything still in the local queue, newest first — backs the queue UI.
  Future<List<CaptureJob>> all() async {
    final batches = await (_db.select(_db.captureBatches)
          ..orderBy([(t) => OrderingTerm.desc(t.capturedAt)]))
        .get();
    return Future.wait(batches.map(_withPages));
  }

  Stream<List<CaptureJob>> watchAll() {
    final query = _db.select(_db.captureBatches)
      ..orderBy([(t) => OrderingTerm.desc(t.capturedAt)]);
    return query.watch().asyncMap(
          (batches) => Future.wait(batches.map(_withPages)),
        );
  }

  Future<CaptureJob?> byId(int batchId) async {
    final batch = await (_db.select(
      _db.captureBatches,
    )..where((t) => t.id.equals(batchId)))
        .getSingleOrNull();
    if (batch == null) return null;
    return _withPages(batch);
  }

  Future<void> markUploading(int batchId) async {
    final attempts = await _attempts(batchId);
    await _update(
      batchId,
      CaptureBatchesCompanion(
        attemptCount: Value(attempts + 1),
        lastError: const Value(null),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }

  /// Records a successful upload and the server id it produced.
  Future<void> markUploaded(int batchId, int importId) => _update(
        batchId,
        CaptureBatchesCompanion(
          importId: Value(importId),
          status: Value(DocumentStatus.uploaded.wire),
          lastError: const Value(null),
          nextAttemptAt: const Value(null),
          updatedAt: Value(DateTime.now()),
        ),
      );

  /// Records a failed attempt and schedules the next one.
  Future<void> markFailed(int batchId, String error) async {
    final attempts = await _attempts(batchId);
    final backoff = retryBackoff[attempts.clamp(0, retryBackoff.length - 1)];
    await _update(
      batchId,
      CaptureBatchesCompanion(
        lastError: Value(error),
        nextAttemptAt: Value(DateTime.now().add(backoff)),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }

  /// Clears backoff and the attempt count so a user-initiated retry runs now,
  /// including for a job that exhausted [maxAttempts].
  Future<void> retryNow(int batchId) => _update(
        batchId,
        CaptureBatchesCompanion(
          status: Value(DocumentStatus.pendingUpload.wire),
          attemptCount: const Value(0),
          lastError: const Value(null),
          nextAttemptAt: const Value(null),
          updatedAt: Value(DateTime.now()),
        ),
      );

  /// Mirrors the server's pipeline status onto the local row so the queue can
  /// be rendered from one source while polling.
  Future<void> syncStatus(int batchId, DocumentStatus status) => _update(
        batchId,
        CaptureBatchesCompanion(
          status: Value(status.wire),
          updatedAt: Value(DateTime.now()),
        ),
      );

  Future<void> markExported(int batchId) => _update(
        batchId,
        CaptureBatchesCompanion(
          isExported: const Value(true),
          updatedAt: Value(DateTime.now()),
        ),
      );

  /// Removes a job and deletes its page images from disk.
  ///
  /// Page rows cascade, but the files are outside the database and would
  /// otherwise accumulate until the user reinstalls.
  Future<void> remove(int batchId) async {
    final job = await byId(batchId);
    if (job == null) return;
    for (final page in job.pages) {
      await _deleteQuietly(page.filePath);
    }
    await (_db.delete(_db.captureBatches)..where((t) => t.id.equals(batchId)))
        .go();
  }

  /// Frees disk for batches whose data is safely on the server and exported.
  /// The rows are kept so history still lists them.
  Future<int> pruneExportedImages() async {
    final batches = await (_db.select(
      _db.captureBatches,
    )..where((t) => t.isExported.equals(true)))
        .get();

    var removed = 0;
    for (final batch in batches) {
      final pages = await _pagesOf(batch.id);
      for (final page in pages) {
        if (await _deleteQuietly(page.filePath)) removed++;
      }
      await (_db.delete(_db.capturePages)
            ..where((t) => t.batchId.equals(batch.id)))
          .go();
    }
    return removed;
  }

  Future<bool> _deleteQuietly(String path) async {
    try {
      final file = File(path);
      if (await file.exists()) {
        await file.delete();
        return true;
      }
    } on FileSystemException {
      // A missing or locked file must not block queue maintenance.
    }
    return false;
  }

  Future<int> _attempts(int batchId) async {
    final row = await (_db.select(
      _db.captureBatches,
    )..where((t) => t.id.equals(batchId)))
        .getSingleOrNull();
    return row?.attemptCount ?? 0;
  }

  Future<List<CapturePage>> _pagesOf(int batchId) =>
      (_db.select(_db.capturePages)
            ..where((t) => t.batchId.equals(batchId))
            ..orderBy([(t) => OrderingTerm.asc(t.pageNumber)]))
          .get();

  Future<CaptureJob> _withPages(CaptureBatch batch) async =>
      CaptureJob(batch: batch, pages: await _pagesOf(batch.id));

  Future<void> _update(int batchId, CaptureBatchesCompanion values) async {
    await (_db.update(_db.captureBatches)..where((t) => t.id.equals(batchId)))
        .write(values);
  }
}

/// A page about to be enqueued.
class CapturePageDraft {
  const CapturePageDraft({
    required this.filePath,
    this.byteSize = 0,
    this.qualityNote,
  });

  final String filePath;
  final int byteSize;
  final String? qualityNote;
}
