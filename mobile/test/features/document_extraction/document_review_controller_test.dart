import 'dart:io';

import 'package:dio/dio.dart';
import 'package:drift/drift.dart' show DatabaseConnection;
import 'package:drift/native.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_review_controller.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_storage.dart';
import 'package:nexora_mobile/features/document_extraction/data/document_extraction_api.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

final _unusedDio = Dio();

class FakeAuthController extends AuthController {
  FakeAuthController(this._state);
  final AuthState _state;

  @override
  AuthState build() => _state;
}

/// Records what review asked the server to do, and can be told to refuse.
class FakeReviewApi extends DocumentExtractionApi {
  // Every method that would reach the network is overridden, so the Dio the
  // superclass holds is never used.
  FakeReviewApi({this.saveError, this.editError, this.validateError})
      : super(_unusedDio);

  final ApiException? saveError;
  final ApiException? editError;
  final ApiException? validateError;

  final headerPatches = <Map<String, dynamic>>[];
  final itemPatches = <(int, Map<String, dynamic>)>[];
  final excluded = <int>[];
  final supplierAssignments = <Map<String, dynamic>>[];
  final stagesRun = <DocumentStage>[];
  final saves = <bool>[];
  final actors = <String?>[];
  int reviewCalls = 0;

  @override
  Future<DocumentReview> review(int importId) async {
    reviewCalls++;
    return DocumentReview.fromJson({
      'import_id': importId,
      'status': 'REVIEW_PENDING',
      'header': {'import_id': importId},
      'items': const [],
    });
  }

  @override
  Future<void> patchHeader(
    int importId,
    Map<String, dynamic> fields, {
    String? actor,
  }) async {
    if (editError != null) throw editError!;
    actors.add(actor);
    headerPatches.add(fields);
  }

  @override
  Future<void> patchItem(
    int importId,
    int itemId,
    Map<String, dynamic> fields, {
    String? actor,
  }) async {
    if (editError != null) throw editError!;
    itemPatches.add((itemId, fields));
  }

  @override
  Future<void> excludeItem(int importId, int itemId, {String? actor}) async {
    if (editError != null) throw editError!;
    excluded.add(itemId);
  }

  @override
  Future<void> assignSupplier(
    int importId,
    Map<String, dynamic> fields, {
    String? actor,
  }) async {
    if (editError != null) throw editError!;
    supplierAssignments.add(fields);
  }

  @override
  Future<void> runStage(
    int importId,
    DocumentStage stage, {
    String? actor,
  }) async {
    if (validateError != null) throw validateError!;
    stagesRun.add(stage);
  }

  @override
  Future<void> save(int importId, {bool force = false, String? actor}) async {
    if (saveError != null) throw saveError!;
    actors.add(actor);
    saves.add(force);
  }
}

void main() {
  late AppDatabase db;
  late FakeReviewApi api;
  late Directory tmp;

  setUp(() async {
    db = AppDatabase.withExecutor(DatabaseConnection(NativeDatabase.memory()));
    api = FakeReviewApi();
    tmp = await Directory.systemTemp.createTemp('review_ctl_test');
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
        reviewActorProvider.overrideWithValue('kavitha'),
        // The queue rebases page paths through storage; the real one reaches
        // path_provider, which has no platform channel under `flutter test`.
        captureStorageProvider.overrideWithValue(CaptureStorage(root: tmp)),
      ],
    );
    addTearDown(c.dispose);
    return c;
  }

  DocumentReviewController controllerOf(ProviderContainer c) =>
      c.read(documentReviewControllerProvider);

  /// A local queue row that has been uploaded and is waiting for review.
  Future<int> queuedBatch(ProviderContainer c, {int importId = 42}) async {
    final repo = c.read(captureQueueRepositoryProvider);
    final batchId = await repo.enqueue(
      tenantId: 't-1',
      pages: const [CapturePageDraft(filePath: '/tmp/none.jpg')],
    );
    await repo.markUploaded(batchId, importId);
    await repo.syncStatus(batchId, DocumentStatus.reviewPending);
    return batchId;
  }

  group('edits', () {
    test('re-check the invoice so the findings match what was just fixed',
        () async {
      // The server stores validation_status from the last validate run and
      // `save` reads that stored value — without a re-check, correcting the
      // missing invoice number leaves the import still marked FAILED and the
      // user is asked to override an error they have already resolved.
      final c = container();

      final result = await controllerOf(c).patchHeader(
        42,
        {'invoice_number': 'INV-9001'},
      );

      expect(result.ok, isTrue);
      expect(api.headerPatches.single, {'invoice_number': 'INV-9001'});
      expect(api.stagesRun, [DocumentStage.validate]);
    });

    test('carry the acting user, so a correction is attributable', () async {
      final c = container();
      await controllerOf(c).patchHeader(42, {'invoice_number': 'INV-1'});
      expect(api.actors, ['kavitha']);
    });

    test('patch one line and re-check', () async {
      final c = container();

      final result = await controllerOf(c).patchItem(42, 7, {'quantity': 12});

      expect(result.ok, isTrue);
      expect(api.itemPatches.single.$1, 7);
      expect(api.stagesRun, [DocumentStage.validate]);
    });

    test('excluding a line re-checks the totals it was part of', () async {
      final c = container();

      await controllerOf(c).excludeItem(42, 7);

      expect(api.excluded, [7]);
      expect(api.stagesRun, [DocumentStage.validate]);
    });

    test('assigning a supplier re-checks the unknown-supplier finding',
        () async {
      final c = container();

      await controllerOf(c).assignSupplier(42, {'supplier_name': 'Acme'});

      expect(api.supplierAssignments.single, {'supplier_name': 'Acme'});
      expect(api.stagesRun, [DocumentStage.validate]);
    });

    test('a failed edit is reported and nothing is re-checked', () async {
      api = FakeReviewApi(
        editError:
            const ApiException(message: 'Item not found', statusCode: 404),
      );
      final c = container();

      final result = await controllerOf(c).patchItem(42, 7, {'quantity': 12});

      expect(result.ok, isFalse);
      expect(result.message, 'Item not found');
      expect(api.stagesRun, isEmpty);
    });

    test(
      'an offline edit is queued rather than lost, and reported as a success '
      'because from the user\'s side it is one',
      () async {
        api = FakeReviewApi(
          editError: const ApiException(message: 'boom', isNetwork: true),
        );
        final c = container();

        final result =
            await controllerOf(c).patchHeader(42, {'net_amount': 10});

        expect(result.ok, isTrue);
        expect(result.queuedOffline, isTrue);
        expect(result.message, contains('sync'));

        final queued = await c.read(outboxRepositoryProvider).forScope(
              reviewScope(42),
            );
        expect(queued, hasLength(1));
        expect(queued.single.kind, ReviewOutboxKinds.header);
        expect(queued.single.decodedPayload['fields'], {'net_amount': 10});
      },
    );

    test(
      'a server refusal is NOT queued — it will be refused again in an hour, '
      'and queueing would turn a clear rejection into a silent dead letter',
      () async {
        api = FakeReviewApi(
          editError: const ApiException(message: 'Quantity must be positive.'),
        );
        final c = container();

        final result = await controllerOf(c).patchItem(42, 7, {'quantity': -1});

        expect(result.ok, isFalse);
        expect(result.queuedOffline, isFalse);
        expect(result.message, 'Quantity must be positive.');
        expect(
          await c.read(outboxRepositoryProvider).forScope(reviewScope(42)),
          isEmpty,
        );
      },
    );

    test('the queued edit carries the actor for the audit trail', () async {
      api = FakeReviewApi(
        editError: const ApiException(message: 'boom', isNetwork: true),
      );
      final c = container();

      await controllerOf(c).excludeItem(42, 7);

      final queued =
          await c.read(outboxRepositoryProvider).forScope(reviewScope(42));
      expect(queued.single.decodedPayload['actor'], 'kavitha');
      expect(queued.single.summary, isNotNull,
          reason: 'a pending change has to be describable later');
    });

    test('a re-check that fails does not undo an edit that worked', () async {
      // The correction is on the server; only the findings are one edit stale.
      api = FakeReviewApi(
        validateError: const ApiException(message: 'validator down'),
      );
      final c = container();

      final result = await controllerOf(c).patchHeader(42, {'net_amount': 10});

      expect(result.ok, isTrue);
      expect(api.headerPatches, hasLength(1));
    });
  });

  group('save', () {
    test('unresolved errors ask for a decision rather than forcing', () async {
      api = FakeReviewApi(
        saveError: const ApiException(
          message: 'Import has unresolved validation errors',
          statusCode: 409,
        ),
      );
      final c = container();

      final result = await controllerOf(c).save(42);

      expect(result.ok, isFalse);
      expect(result.blockedByErrors, isTrue);
      expect(api.saves, isEmpty,
          reason: 'force is the user\'s call, not a retry');
    });

    test('an override is sent only when asked for', () async {
      final c = container();

      final result = await controllerOf(c).save(42, force: true);

      expect(result.ok, isTrue);
      expect(api.saves, [true]);
      expect(result.message, contains('overridden'));
    });

    test('marks the local queue row saved so it leaves the review list',
        () async {
      // Nothing else would: the queue poller only follows documents the server
      // is still working on, and REVIEW_PENDING is not one of them.
      final c = container();
      final batchId = await queuedBatch(c);

      final result = await controllerOf(c).save(42, batchId: batchId);

      expect(result.ok, isTrue);
      final job = await c.read(captureQueueRepositoryProvider).byId(batchId);
      expect(job!.status, DocumentStatus.saved);
    });

    test('a network failure leaves the queue row alone', () async {
      api = FakeReviewApi(
        saveError: const ApiException(message: 'no route', isNetwork: true),
      );
      final c = container();
      final batchId = await queuedBatch(c);

      final result = await controllerOf(c).save(42, batchId: batchId);

      expect(result.ok, isFalse);
      expect(result.message, contains('nothing was saved'));
      final job = await c.read(captureQueueRepositoryProvider).byId(batchId);
      expect(job!.status, DocumentStatus.reviewPending);
    });

    test('a review opened outside the queue saves without a batch', () async {
      final c = container();

      final result = await controllerOf(c).save(42);

      expect(result.ok, isTrue);
      expect(api.saves, [false]);
    });
  });

  group('documentReviewProvider', () {
    test('reads the payload for one import', () async {
      final c = container();

      final review = await c.read(documentReviewProvider(42).future);

      expect(review.importId, 42);
      expect(review.status, DocumentStatus.reviewPending);
      expect(api.reviewCalls, 1);
    });

    test('refresh re-reads it', () async {
      final c = container();
      await c.read(documentReviewProvider(42).future);

      await controllerOf(c).refresh(42);

      expect(api.reviewCalls, 2);
    });
  });

  group('the actor an edit is recorded against', () {
    /// Every audit column the actor reaches is a SQL UNIQUEIDENTIFIER, and
    /// `save` writes it through without coercing. A username there does not
    /// get recorded as a name — it fails conversion and 500s the request, so
    /// this has to be the id. Every other test in this file overrides the
    /// provider with a literal, which is exactly how the wiring went unchecked.
    test('is the user id, not the username', () {
      final c = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith(
            () => FakeAuthController(
              const AuthState(
                status: AuthStatus.authenticated,
                user: AppUser(
                  userId: '8f1d4b2a-0c73-4e59-9a61-2b7c5d0e3a44',
                  username: 'superadmin',
                ),
              ),
            ),
          ),
        ],
      );
      addTearDown(c.dispose);

      expect(
          c.read(reviewActorProvider), '8f1d4b2a-0c73-4e59-9a61-2b7c5d0e3a44');
    });

    test('is null when nobody is signed in', () {
      final c = ProviderContainer(
        overrides: [
          authControllerProvider.overrideWith(() => FakeAuthController(
                const AuthState(status: AuthStatus.unauthenticated),
              )),
        ],
      );
      addTearDown(c.dispose);

      expect(c.read(reviewActorProvider), isNull);
    });
  });
}
