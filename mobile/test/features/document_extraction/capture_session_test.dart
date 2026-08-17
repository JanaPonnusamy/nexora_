import 'dart:io';
import 'dart:typed_data';

import 'package:drift/drift.dart' show DatabaseConnection;
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_session_controller.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_processor.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_storage.dart';
import 'package:nexora_mobile/features/document_extraction/domain/capture_quality.dart';

/// Stands in for the isolate-backed decode so the session's own behaviour —
/// file ownership, ordering, the hand-off to the queue — is what is under
/// test. The heuristics themselves are covered by `capture_processor_test`.
class FakeProcessor extends CaptureProcessor {
  const FakeProcessor(
      {this.quality = CaptureQuality.unknown, this.fails = false});

  final CaptureQuality quality;
  final bool fails;

  @override
  Future<ProcessedCapture?> process(Uint8List bytes) async {
    if (fails) return null;
    return ProcessedCapture(
      jpegBytes: bytes,
      quality: quality,
      width: 1600,
      height: 2000,
    );
  }
}

class FakeAuthController extends AuthController {
  FakeAuthController(this._state);
  final AuthState _state;

  @override
  AuthState build() => _state;
}

const _blurred = CaptureQuality(
  sharpness: 12,
  glareRatio: 0,
  brightness: 140,
  sourceWidth: 1600,
  sourceHeight: 2000,
  findings: [QualityFinding(QualityIssue.blurred, QualityVerdict.reject)],
);

void main() {
  late AppDatabase db;
  late Directory tmp;

  const user = AppUser(userId: 'u1', username: 'field', tenantId: 't-1');

  setUp(() async {
    db = AppDatabase.withExecutor(DatabaseConnection(NativeDatabase.memory()));
    tmp = await Directory.systemTemp.createTemp('capture_session_test');
  });

  tearDown(() async {
    await db.close();
    if (tmp.existsSync()) await tmp.delete(recursive: true);
  });

  ProviderContainer container({
    CaptureProcessor processor = const FakeProcessor(),
    AuthState auth = const AuthState(
      status: AuthStatus.authenticated,
      user: user,
    ),
  }) {
    final c = ProviderContainer(
      overrides: [
        appDatabaseProvider.overrideWithValue(db),
        captureStorageProvider.overrideWithValue(CaptureStorage(root: tmp)),
        captureProcessorProvider.overrideWithValue(processor),
        authControllerProvider.overrideWith(() => FakeAuthController(auth)),
      ],
    );
    addTearDown(c.dispose);
    return c;
  }

  /// A stand-in for a file the camera plugin just wrote to its temp directory.
  Future<File> shot(String name) async {
    final file = File('${tmp.path}/$name');
    await file.writeAsBytes(Uint8List.fromList([1, 2, 3, 4]));
    return file;
  }

  group('addPage', () {
    test('stores the processed page and reports its quality', () async {
      final c = container(processor: const FakeProcessor(quality: _blurred));
      final session = c.read(captureSessionProvider.notifier);

      final page = await session.addPage(await shot('a.jpg'));

      expect(page, isNotNull);
      expect(page!.quality.verdict, QualityVerdict.reject);
      expect(page.byteSize, 4);
      expect(File(page.filePath).existsSync(), isTrue);

      final state = c.read(captureSessionProvider);
      expect(state.pageCount, 1);
      expect(state.flaggedCount, 1);
      expect(state.busy, isFalse);
    });

    test('writes into the session directory, not the source location',
        () async {
      final c = container();
      final page = await c
          .read(captureSessionProvider.notifier)
          .addPage(await shot('a.jpg'));

      final sessionId = c.read(captureSessionProvider).sessionId;
      expect(page!.filePath, contains('captures/$sessionId/'));
      expect(page.filePath, endsWith('.jpg'));
    });

    test('an undecodable file is reported, not silently dropped', () async {
      final c = container(processor: const FakeProcessor(fails: true));

      final page = await c
          .read(captureSessionProvider.notifier)
          .addPage(await shot('a.bin'));

      expect(page, isNull);
      final state = c.read(captureSessionProvider);
      expect(state.isEmpty, isTrue);
      expect(state.error, isNotNull);
      expect(state.busy, isFalse);
    });

    test('pages accumulate in capture order', () async {
      final c = container();
      final session = c.read(captureSessionProvider.notifier);

      await session.addPage(await shot('a.jpg'));
      await session.addPage(await shot('b.jpg'));
      await session.addPage(await shot('c.jpg'));

      final paths =
          c.read(captureSessionProvider).pages.map((p) => p.filePath).toList();
      expect(paths, hasLength(3));
      expect(paths[0], contains('page_01'));
      expect(paths[1], contains('page_02'));
      expect(paths[2], contains('page_03'));
    });
  });

  group('editing', () {
    test('removePage deletes the image from disk', () async {
      final c = container();
      final session = c.read(captureSessionProvider.notifier);
      final page = await session.addPage(await shot('a.jpg'));

      await session.removePage(0);

      expect(c.read(captureSessionProvider).isEmpty, isTrue);
      expect(File(page!.filePath).existsSync(), isFalse);
    });

    test('removePage ignores an index that is not there', () async {
      final c = container();
      final session = c.read(captureSessionProvider.notifier);
      await session.addPage(await shot('a.jpg'));

      await session.removePage(5);
      await session.removePage(-1);

      expect(c.read(captureSessionProvider).pageCount, 1);
    });

    test('reorder moves a page within the document', () async {
      final c = container();
      final session = c.read(captureSessionProvider.notifier);
      await session.addPage(await shot('a.jpg'));
      await session.addPage(await shot('b.jpg'));
      await session.addPage(await shot('c.jpg'));

      session.reorder(2, 0);

      final paths =
          c.read(captureSessionProvider).pages.map((p) => p.filePath).toList();
      expect(paths[0], contains('page_03'));
      expect(paths[1], contains('page_01'));
    });
  });

  group('commit', () {
    test('queues a batch carrying page order and quality notes', () async {
      final c = container(processor: const FakeProcessor(quality: _blurred));
      final session = c.read(captureSessionProvider.notifier);
      await session.addPage(await shot('a.jpg'));
      await session.addPage(await shot('b.jpg'));

      final batchId = await session.commit();

      expect(batchId, isNotNull);
      final job = await c.read(captureQueueRepositoryProvider).byId(batchId!);
      expect(job!.batch.tenantId, 't-1');
      expect(job.batch.pageCount, 2);
      expect(job.pages.map((p) => p.pageNumber), [1, 2]);
      expect(job.pages.first.qualityNote, 'reject: Blurry');
    });

    test('the queue takes ownership of the files', () async {
      final c = container();
      final session = c.read(captureSessionProvider.notifier);
      final page = await session.addPage(await shot('a.jpg'));

      await session.commit();

      // Resetting the session must not take the pages with it — they are
      // waiting to upload.
      expect(File(page!.filePath).existsSync(), isTrue);
    });

    test('starts a fresh session so a later discard cannot delete queued pages',
        () async {
      final c = container();
      final session = c.read(captureSessionProvider.notifier);
      final before = c.read(captureSessionProvider).sessionId;
      final page = await session.addPage(await shot('a.jpg'));

      await session.commit();
      final after = c.read(captureSessionProvider).sessionId;
      await session.discard();

      expect(after, isNot(before));
      expect(c.read(captureSessionProvider).isEmpty, isTrue);
      expect(File(page!.filePath).existsSync(), isTrue);
    });

    test('an empty session commits nothing', () async {
      final c = container();
      expect(await c.read(captureSessionProvider.notifier).commit(), isNull);
    });

    test('falls back to the store tenant when the user has none', () async {
      final c = container(
        auth: const AuthState(
          status: AuthStatus.authenticated,
          user: AppUser(userId: 'u1', username: 'field'),
          selectedStore: SelectedStore(
            storeId: 's-9',
            storeName: 'Nathan Medicals A',
            tenantId: 't-2',
          ),
        ),
      );
      final session = c.read(captureSessionProvider.notifier);
      await session.addPage(await shot('a.jpg'));

      final batchId = await session.commit();

      final job = await c.read(captureQueueRepositoryProvider).byId(batchId!);
      expect(job!.batch.tenantId, 't-2');
      expect(job.batch.storeId, 's-9');
    });

    test('refuses to queue a batch with no tenant to file it under', () async {
      final c = container(
        auth: const AuthState(
          status: AuthStatus.authenticated,
          user: AppUser(userId: 'u1', username: 'field'),
        ),
      );
      final session = c.read(captureSessionProvider.notifier);
      await session.addPage(await shot('a.jpg'));

      final batchId = await session.commit();

      expect(batchId, isNull);
      expect(c.read(captureSessionProvider).error, isNotNull);
      // The pages stay put so the user can retry after re-authenticating.
      expect(c.read(captureSessionProvider).pageCount, 1);
    });
  });

  group('discard', () {
    test('deletes every page of an abandoned capture', () async {
      final c = container();
      final session = c.read(captureSessionProvider.notifier);
      final a = await session.addPage(await shot('a.jpg'));
      final b = await session.addPage(await shot('b.jpg'));

      await session.discard();

      expect(c.read(captureSessionProvider).isEmpty, isTrue);
      expect(File(a!.filePath).existsSync(), isFalse);
      expect(File(b!.filePath).existsSync(), isFalse);
    });
  });

  group('storage housekeeping', () {
    test('sweepEmptySessions reclaims directories a crash orphaned', () async {
      final storage = CaptureStorage(root: tmp);
      await storage.writePage(
        sessionId: 'live',
        pageNumber: 1,
        bytes: Uint8List.fromList([1]),
      );
      Directory('${tmp.path}/captures/orphan').createSync(recursive: true);

      expect(await storage.sweepEmptySessions(), 1);
      expect(Directory('${tmp.path}/captures/orphan').existsSync(), isFalse);
      expect(Directory('${tmp.path}/captures/live').existsSync(), isTrue);
    });
  });
}
