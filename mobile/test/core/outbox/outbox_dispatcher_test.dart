import 'package:drift/drift.dart' show DatabaseConnection;
import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/outbox/outbox_dispatcher.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';

class _FakeConnectivity extends ConnectivityService {
  bool online = true;

  @override
  Future<NetworkStatus> check() async =>
      online ? NetworkStatus.online : NetworkStatus.offline;

  @override
  Future<void> start() async {}
}

const _offline = ApiException(message: 'No connection.', isNetwork: true);
const _rejected = ApiException(message: 'Quantity must be positive.');

void main() {
  late AppDatabase db;
  late OutboxRepository outbox;
  late _FakeConnectivity connectivity;
  late OutboxDispatcher dispatcher;

  setUp(() {
    db = AppDatabase.withExecutor(DatabaseConnection(NativeDatabase.memory()));
    outbox = OutboxRepository(db);
    connectivity = _FakeConnectivity();
    dispatcher = OutboxDispatcher(outbox: outbox, connectivity: connectivity);
  });

  tearDown(() => db.close());

  Future<int> enqueue({
    String kind = 'document.header',
    String scope = 'import:1',
    Map<String, dynamic> payload = const {'importId': 1},
  }) =>
      outbox.enqueue(kind: kind, scope: scope, payload: payload);

  test('sends a queued edit and marks it delivered', () async {
    final sent = <Map<String, dynamic>>[];
    dispatcher.register('document.header', (p) async => sent.add(p));
    final id = await enqueue(payload: {'importId': 42});

    final report = await dispatcher.drain();

    expect(report.sent, 1);
    expect(sent.single['importId'], 42);
    expect((await outbox.byId(id))!.parsedStatus, OutboxStatus.done);
  });

  test('applies a scope\'s entries in the order they were made', () async {
    final order = <String>[];
    dispatcher.register(
      'document.header',
      (p) async => order.add(p['tag'] as String),
    );
    await enqueue(payload: {'importId': 1, 'tag': 'first'});
    await enqueue(payload: {'importId': 1, 'tag': 'second'});
    await enqueue(payload: {'importId': 1, 'tag': 'third'});

    final report = await dispatcher.drain();

    expect(report.sent, 3);
    expect(order, ['first', 'second', 'third']);
  });

  test('does nothing while offline, and does not call it a failure', () async {
    connectivity.online = false;
    var called = false;
    dispatcher.register('document.header', (_) async => called = true);
    final id = await enqueue();

    final report = await dispatcher.drain();

    expect(report.skippedOffline, isTrue);
    expect(report.failed, 0);
    expect(called, isFalse);
    expect((await outbox.byId(id))!.attemptCount, 0);
  });

  test(
    'a network failure mid-drain does not burn an attempt — a tunnel must not '
    'march a good edit towards being given up on',
    () async {
      dispatcher.register('document.header', (_) async => throw _offline);
      final id = await enqueue();

      await dispatcher.drain();

      final entry = (await outbox.byId(id))!;
      expect(entry.attemptCount, 0);
      expect(entry.parsedStatus, OutboxStatus.pending);
    },
  );

  test('a server rejection counts as an attempt and backs off', () async {
    dispatcher.register('document.header', (_) async => throw _rejected);
    final id = await enqueue();

    final report = await dispatcher.drain();

    expect(report.failed, 1);
    final entry = (await outbox.byId(id))!;
    expect(entry.attemptCount, 1);
    expect(entry.lastError, 'Quantity must be positive.');
    expect(entry.nextAttemptAt, isNotNull);
  });

  test('a failing entry blocks its scope but not the others', () async {
    final sent = <String>[];
    dispatcher.register('document.header', (p) async {
      if (p['scope'] == 'bad') throw _rejected;
      sent.add(p['scope'] as String);
    });
    await enqueue(scope: 'import:1', payload: {'importId': 1, 'scope': 'bad'});
    await enqueue(
        scope: 'import:1', payload: {'importId': 1, 'scope': 'after'});
    await enqueue(
        scope: 'import:2', payload: {'importId': 2, 'scope': 'other'});

    await dispatcher.drain();

    expect(sent, ['other'],
        reason: 'the entry behind a failure must wait its turn');
  });

  test(
    'an unknown kind is given up on immediately rather than retried — an older '
    'build queued something this one cannot send, and waiting cannot fix it',
    () async {
      final id = await enqueue(kind: 'procurement.something-new');

      final report = await dispatcher.drain();

      expect(report.deadLettered, 1);
      final entry = (await outbox.byId(id))!;
      expect(entry.parsedStatus, OutboxStatus.deadLetter);
      expect(entry.lastError, contains('cannot send'));
    },
  );

  test('a handler bug dead-letters instead of retrying forever', () async {
    dispatcher.register(
      'document.header',
      (_) async => throw StateError('null importId'),
    );
    final id = await enqueue();

    final report = await dispatcher.drain();

    expect(report.deadLettered, 1);
    expect((await outbox.byId(id))!.parsedStatus, OutboxStatus.deadLetter);
  });

  test('concurrent drains collapse, so nothing is sent twice', () async {
    var calls = 0;
    dispatcher.register('document.header', (_) async {
      calls++;
      await Future<void>.delayed(const Duration(milliseconds: 20));
    });
    await enqueue();

    await Future.wait([dispatcher.drain(), dispatcher.drain()]);

    expect(calls, 1);
  });

  test('an empty outbox is a no-op', () async {
    final report = await dispatcher.drain();
    expect(report.didWork, isFalse);
    expect(report.sent, 0);
  });
}
