import 'dart:io';
import 'dart:ui' show Rect;

import 'package:dio/dio.dart';
import 'package:drift/drift.dart' show DatabaseConnection;
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_export_controller.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_review_controller.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/data/document_extraction_api.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

final _unusedDio = Dio();

/// Stands in for `/exports` and its download, and can be told to refuse.
class FakeExportApi extends DocumentExtractionApi {
  FakeExportApi({
    this.createError,
    this.downloadError,
    this.bytes = const [80, 75, 3, 4],
    this.rowCount = 12,
    this.exportBatchId = 'batch-1',
  }) : super(_unusedDio);

  final ApiException? createError;
  final ApiException? downloadError;
  final List<int> bytes;
  final int rowCount;
  final String exportBatchId;

  final requested = <List<int>>[];
  final downloaded = <String>[];
  final actors = <String?>[];

  @override
  Future<ExportBatch> createExport({
    required List<int> importIds,
    String fileFormat = 'xlsx',
    String? actor,
  }) async {
    if (createError != null) throw createError!;
    requested.add(importIds);
    actors.add(actor);
    return ExportBatch.fromJson({
      'export_batch_id': exportBatchId,
      'row_count': rowCount,
      'file_format': fileFormat,
      'download_url':
          '/api/document-extraction/exports/$exportBatchId/download',
    });
  }

  @override
  Future<List<int>> downloadExport(String exportBatchId) async {
    if (downloadError != null) throw downloadError!;
    downloaded.add(exportBatchId);
    return bytes;
  }
}

void main() {
  late AppDatabase db;
  late Directory tmp;
  late FakeExportApi api;
  late List<File> shared;
  late List<String?> subjects;
  Object? shareError;

  setUp(() async {
    db = AppDatabase.withExecutor(DatabaseConnection(NativeDatabase.memory()));
    tmp = await Directory.systemTemp.createTemp('export_ctl_test');
    api = FakeExportApi();
    shared = [];
    subjects = [];
    shareError = null;
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
        exportDirectoryProvider.overrideWithValue(() async => tmp),
        fileSharerProvider.overrideWithValue(
          (File file, {String? subject, Rect? sharePositionOrigin}) async {
            if (shareError != null) throw shareError!;
            shared.add(file);
            subjects.add(subject);
          },
        ),
      ],
    );
    addTearDown(c.dispose);
    return c;
  }

  DocumentExportController controllerOf(ProviderContainer c) =>
      c.read(documentExportControllerProvider);

  /// A local queue row that has been uploaded, reviewed and saved.
  Future<int> savedBatch(ProviderContainer c, {required int importId}) async {
    final repo = c.read(captureQueueRepositoryProvider);
    final page = File('${tmp.path}/page-$importId.jpg')
      ..writeAsBytesSync([1, 2, 3]);
    final batchId = await repo.enqueue(
      tenantId: 't-1',
      pages: [CapturePageDraft(filePath: page.path, byteSize: 3)],
    );
    await repo.markUploaded(batchId, importId);
    await repo.syncStatus(batchId, DocumentStatus.saved);
    return batchId;
  }

  group('exportAndShare', () {
    test('one workbook covers every invoice asked for', () async {
      // The export contract puts a batch into a single five-sheet workbook —
      // one call with all the ids, not a file per invoice.
      final c = container();

      final outcome = await controllerOf(c).exportAndShare(
        importIds: [11, 12, 13],
      );

      expect(outcome.ok, isTrue);
      expect(api.requested.single, [11, 12, 13]);
      expect(api.downloaded, ['batch-1']);
      expect(shared, hasLength(1));
      expect(outcome.message, 'Workbook shared — 3 invoices, 12 lines.');
    });

    test('writes the bytes the server built, untouched', () async {
      api = FakeExportApi(bytes: const [80, 75, 3, 4, 20, 0]);
      final c = container();

      await controllerOf(c).exportAndShare(importIds: [11]);

      expect(shared.single.readAsBytesSync(), [80, 75, 3, 4, 20, 0]);
      expect(shared.single.path, endsWith('.xlsx'));
    });

    test('names the file after the invoice, not the export uuid', () async {
      // The server serves it as `<uuid>.xlsx`; a workbook landing in someone's
      // chat under that name tells them nothing.
      final c = container();

      await controllerOf(c).exportAndShare(
        importIds: [11],
        fileLabel: 'SI/26-27/4821',
      );

      final name = shared.single.uri.pathSegments.last;
      expect(name, startsWith('axythic-SI-26-27-4821-'));
      expect(name, endsWith('.xlsx'));
      // Slashes and spaces do not survive being part of a file name.
      expect(name, isNot(contains('/')));
    });

    test('marks the local rows exported so their images can be reclaimed',
        () async {
      final c = container();
      final first = await savedBatch(c, importId: 11);
      final second = await savedBatch(c, importId: 12);

      final outcome = await controllerOf(c).exportAndShare(
        importIds: [11, 12],
        batchIds: [first, second],
      );

      expect(outcome.ok, isTrue);
      final repo = c.read(captureQueueRepositoryProvider);
      for (final batchId in [first, second]) {
        final job = await repo.byId(batchId);
        expect(job!.status, DocumentStatus.exported, reason: 'batch $batchId');
        expect(job.batch.isExported, isTrue, reason: 'batch $batchId');
      }
      // The flag is what "Free up space" acts on.
      expect(await repo.pruneExportedImages(), 2);
    });

    test('carries the acting user for the export audit trail', () async {
      final c = ProviderContainer(
        overrides: [
          appDatabaseProvider.overrideWithValue(db),
          documentExtractionApiProvider.overrideWithValue(api),
          exportDirectoryProvider.overrideWithValue(() async => tmp),
          fileSharerProvider.overrideWithValue(
            (File file, {String? subject, Rect? sharePositionOrigin}) async {},
          ),
          reviewActorProvider.overrideWithValue('kavitha'),
        ],
      );
      addTearDown(c.dispose);

      await c.read(documentExportControllerProvider).exportAndShare(
        importIds: [11],
      );

      expect(api.actors, ['kavitha']);
    });

    test('an offline export creates nothing and says so', () async {
      api = FakeExportApi(
        createError: const ApiException(message: 'no route', isNetwork: true),
      );
      final c = container();
      final batchId = await savedBatch(c, importId: 11);

      final outcome = await controllerOf(c).exportAndShare(
        importIds: [11],
        batchIds: [batchId],
      );

      expect(outcome.ok, isFalse);
      expect(outcome.message, contains('no workbook was created'));
      expect(shared, isEmpty);
      // The document is still saved and still owes an export.
      final job = await c.read(captureQueueRepositoryProvider).byId(batchId);
      expect(job!.status, DocumentStatus.saved);
      expect(job.batch.isExported, isFalse);
    });

    test('a download failure is reported rather than sharing nothing',
        () async {
      api = FakeExportApi(
        downloadError: const ApiException(
          message: 'Export not found',
          statusCode: 404,
        ),
      );
      final c = container();

      final outcome = await controllerOf(c).exportAndShare(importIds: [11]);

      expect(outcome.ok, isFalse);
      expect(outcome.message, 'Export not found');
      expect(shared, isEmpty);
    });

    test('an empty workbook is not passed off as a successful export',
        () async {
      api = FakeExportApi(bytes: const []);
      final c = container();
      final batchId = await savedBatch(c, importId: 11);

      final outcome = await controllerOf(c).exportAndShare(
        importIds: [11],
        batchIds: [batchId],
      );

      expect(outcome.ok, isFalse);
      expect(outcome.message, 'The workbook came back empty.');
      expect(shared, isEmpty);
      final job = await c.read(captureQueueRepositoryProvider).byId(batchId);
      expect(job!.batch.isExported, isFalse);
    });

    test('a share sheet that fails still leaves the workbook on the device',
        () async {
      // The export happened on the server either way, so the file is real and
      // worth keeping — the user is told what went wrong, not that it failed.
      shareError = Exception('no activity found');
      final c = container();
      final batchId = await savedBatch(c, importId: 11);

      final outcome = await controllerOf(c).exportAndShare(
        importIds: [11],
        batchIds: [batchId],
      );

      expect(outcome.ok, isFalse);
      expect(outcome.message, contains('could not be shared'));
      expect(outcome.filePath, isNotNull);
      expect(File(outcome.filePath!).existsSync(), isTrue);
      final job = await c.read(captureQueueRepositoryProvider).byId(batchId);
      expect(
        job!.status,
        DocumentStatus.exported,
        reason: 'the server exported it regardless of the share sheet',
      );
    });

    test('nothing selected is refused before any call is made', () async {
      final c = container();

      final outcome = await controllerOf(c).exportAndShare(importIds: []);

      expect(outcome.ok, isFalse);
      expect(api.requested, isEmpty);
    });

    test('a single invoice reads as one, not as a batch', () async {
      api = FakeExportApi(rowCount: 1);
      final c = container();

      final outcome = await controllerOf(c).exportAndShare(importIds: [11]);

      expect(outcome.message, 'Workbook shared — 1 line.');
    });
  });
}
