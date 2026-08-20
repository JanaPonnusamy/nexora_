import 'package:drift/drift.dart' show DatabaseConnection;
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';

void main() {
  late AppDatabase db;
  late OutboxRepository outbox;

  setUp(() {
    db = AppDatabase.withExecutor(DatabaseConnection(NativeDatabase.memory()));
    outbox = OutboxRepository(db);
  });

  tearDown(() => db.close());

  Future<int> enqueue(String kind, String scope) =>
      outbox.enqueue(kind: kind, scope: scope, payload: {'v': kind});

  group('ordering', () {
    test(
      'only the oldest entry per scope is due — two edits of one document '
      'must never be sent concurrently',
      () async {
        final first = await enqueue('document.header', 'import:1');
        await enqueue('document.item', 'import:1');

        final due = await outbox.due();

        expect(due.map((e) => e.id), [first]);
      },
    );

    test('separate scopes are independent', () async {
      final a = await enqueue('document.header', 'import:1');
      final b = await enqueue('document.header', 'import:2');

      final due = await outbox.due();

      expect(due.map((e) => e.id).toSet(), {a, b});
    });

    test('the next entry in a scope becomes due once the first is done',
        () async {
      final first = await enqueue('document.header', 'import:1');
      final second = await enqueue('document.item', 'import:1');

      await outbox.markDone(first);

      final due = await outbox.due();
      expect(due.map((e) => e.id), [second]);
    });

    test(
      'a backed-off entry blocks its whole scope — running the one behind it '
      'would apply the edits out of order',
      () async {
        final first = await enqueue('document.header', 'import:1');
        await enqueue('document.item', 'import:1');
        await outbox.markFailed(first, 'server hiccup');

        expect(await outbox.due(), isEmpty);

        // Once the backoff elapses, the first is due again — not the second.
        final later = DateTime.now().add(const Duration(hours: 2));
        final due = await outbox.due(now: later);
        expect(due.map((e) => e.id), [first]);
      },
    );

    test('a dead-lettered entry unblocks the rest of its scope', () async {
      final first = await enqueue('document.header', 'import:1');
      final second = await enqueue('document.item', 'import:1');
      await outbox.deadLetter(first, 'gave up');

      final due = await outbox.due();

      expect(due.map((e) => e.id), [second],
          reason: 'one unsendable change must not strand every later one');
    });
  });

  group('retry and give-up', () {
    test('backoff lengthens with each attempt', () async {
      final id = await enqueue('document.header', 'import:1');

      await outbox.markFailed(id, 'first');
      final afterOne = (await outbox.byId(id))!.nextAttemptAt!;
      await outbox.markFailed(id, 'second');
      final afterTwo = (await outbox.byId(id))!.nextAttemptAt!;

      expect(afterTwo.isAfter(afterOne), isTrue);
    });

    test('gives up after maxAttempts and says why', () async {
      final id = await enqueue('document.header', 'import:1');

      OutboxStatus? status;
      for (var i = 0; i < OutboxRepository.maxAttempts; i++) {
        status = await outbox.markFailed(id, 'rejected');
      }

      expect(status, OutboxStatus.deadLetter);
      final entry = (await outbox.byId(id))!;
      expect(entry.parsedStatus, OutboxStatus.deadLetter);
      expect(entry.lastError, 'rejected');
      expect(entry.nextAttemptAt, isNull,
          reason: 'a given-up entry must not look scheduled');
    });

    test('retryNow clears the give-up so a user can push it again', () async {
      final id = await enqueue('document.header', 'import:1');
      for (var i = 0; i < OutboxRepository.maxAttempts; i++) {
        await outbox.markFailed(id, 'rejected');
      }

      await outbox.retryNow(id);

      final entry = (await outbox.byId(id))!;
      expect(entry.parsedStatus, OutboxStatus.pending);
      expect(entry.attemptCount, 0);
      expect(entry.lastError, isNull);
      expect(await outbox.due(), hasLength(1));
    });
  });

  group('crash recovery', () {
    test(
      'an entry left in flight by a kill is requeued, not stranded — the app '
      'can be terminated between marking it and reading the response',
      () async {
        final id = await enqueue('document.header', 'import:1');
        await outbox.markInFlight(id);
        expect(await outbox.due(), isEmpty);

        final recovered = await outbox.requeueInterrupted();

        expect(recovered, 1);
        expect((await outbox.byId(id))!.parsedStatus, OutboxStatus.pending);
        expect(await outbox.due(), hasLength(1));
      },
    );
  });

  group('housekeeping', () {
    test('outstanding excludes delivered entries', () async {
      final sent = await enqueue('document.header', 'import:1');
      await enqueue('document.item', 'import:2');
      await outbox.markDone(sent);

      expect(await outbox.outstanding(), hasLength(1));
    });

    test('delivered entries are kept a while, then pruned', () async {
      final id = await enqueue('document.header', 'import:1');
      await outbox.markDone(id);

      expect(await outbox.pruneDelivered(), 0,
          reason: '"your change was sent" must still be there when they look');

      // A negative window puts the cutoff slightly in the future. Drift stores
      // DateTime at second precision, so `Duration.zero` would compare a row
      // written this second against a cutoff in the same second and prune
      // nothing — a property of the test clock, not of the behaviour.
      expect(
        await outbox.pruneDelivered(olderThan: const Duration(seconds: -5)),
        1,
      );
    });

    test('forScope lists what is still owed for one document', () async {
      await enqueue('document.header', 'import:1');
      await enqueue('document.item', 'import:1');
      await enqueue('document.header', 'import:2');

      expect(await outbox.forScope('import:1'), hasLength(2));
      expect(await outbox.forScope('import:2'), hasLength(1));
    });

    test('the payload survives the round trip', () async {
      final id = await outbox.enqueue(
        kind: 'document.item',
        scope: 'import:7',
        payload: {
          'importId': 7,
          'itemId': 12,
          'fields': {'quantity': 40, 'batch_number': 'PC24A1'},
        },
        summary: 'A line on this invoice',
      );

      final entry = (await outbox.byId(id))!;
      expect(entry.decodedPayload['importId'], 7);
      expect(entry.decodedPayload['fields']['batch_number'], 'PC24A1');
      expect(entry.summary, 'A line on this invoice');
    });
  });
}
