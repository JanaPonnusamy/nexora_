import 'dart:convert';

import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';

/// Lifecycle of an outbox entry.
enum OutboxStatus {
  /// Waiting to be sent, or waiting out a backoff.
  pending,

  /// A send is in progress right now.
  inFlight,

  /// The server accepted it. Kept briefly so the UI can say "sent".
  done,

  /// Given up after [OutboxRepository.maxAttempts]. Needs a person.
  deadLetter;

  static OutboxStatus parse(String value) => OutboxStatus.values.firstWhere(
        (s) => s.name == value,
        // An unknown status is treated as still-owed rather than as finished:
        // re-sending something the server already has is recoverable, quietly
        // dropping a user's edit is not.
        orElse: () => OutboxStatus.pending,
      );
}

/// Durable, ordered store of edits that have not reached the server.
///
/// The invariant that matters: **within a scope, entries are applied strictly
/// in order and one at a time.** Without it, two offline edits to the same
/// field can land in either order, and the value the user last typed is not
/// necessarily the one that survives.
class OutboxRepository {
  OutboxRepository(this._db);

  final AppDatabase _db;

  /// Backoff between attempts. Longer than the capture queue's: an outbox entry
  /// is a few hundred bytes, so the cost of waiting is low and the cost of
  /// hammering a struggling server with retries from every device is not.
  static const List<Duration> retryBackoff = [
    Duration(seconds: 15),
    Duration(minutes: 1),
    Duration(minutes: 5),
    Duration(minutes: 20),
    Duration(hours: 1),
  ];

  /// After this many failures an entry stops retrying and asks for a person.
  /// A change that can never succeed — a deleted import, a rejected value —
  /// would otherwise retry until the user uninstalls the app.
  static const int maxAttempts = 8;

  /// Records an intent to change something on the server.
  Future<int> enqueue({
    required String kind,
    required String scope,
    Map<String, dynamic> payload = const {},
    String? summary,
  }) =>
      _db.into(_db.outboxEntries).insert(
            OutboxEntriesCompanion.insert(
              kind: kind,
              scope: scope,
              payload: Value(jsonEncode(payload)),
              summary: Value(summary),
            ),
          );

  /// The next entry to attempt in each scope, oldest scope first.
  ///
  /// One per scope, deliberately. Returning every ready entry would let the
  /// dispatcher run two edits of the same document concurrently, which is
  /// exactly the ordering guarantee this class exists to provide.
  Future<List<OutboxEntry>> due({DateTime? now}) async {
    final at = now ?? DateTime.now();

    final ready = await (_db.select(_db.outboxEntries)
          ..where((t) => t.status.equals(OutboxStatus.pending.name))
          ..orderBy([
            (t) => OrderingTerm.asc(t.createdAt),
            (t) => OrderingTerm.asc(t.id),
          ]))
        .get();

    final firstPerScope = <String, OutboxEntry>{};
    final blocked = <String>{};

    for (final entry in ready) {
      // The oldest pending entry in a scope is the only candidate. If it is
      // still backing off, the whole scope waits — running the one behind it
      // would apply the user's edits out of order.
      if (firstPerScope.containsKey(entry.scope) ||
          blocked.contains(entry.scope)) {
        continue;
      }
      final waiting =
          entry.nextAttemptAt != null && entry.nextAttemptAt!.isAfter(at);
      if (waiting) {
        blocked.add(entry.scope);
      } else {
        firstPerScope[entry.scope] = entry;
      }
    }

    return firstPerScope.values.toList(growable: false);
  }

  /// Everything not yet delivered, newest first — backs the pending-changes UI.
  Future<List<OutboxEntry>> outstanding() => (_db.select(_db.outboxEntries)
        ..where((t) => t.status.isNotValue(OutboxStatus.done.name))
        ..orderBy([(t) => OrderingTerm.desc(t.createdAt)]))
      .get();

  Stream<List<OutboxEntry>> watchOutstanding() => (_db.select(_db.outboxEntries)
        ..where((t) => t.status.isNotValue(OutboxStatus.done.name))
        ..orderBy([(t) => OrderingTerm.desc(t.createdAt)]))
      .watch();

  /// Pending entries for one scope, oldest first — lets a screen show the user
  /// which of their changes to *this* document are still owed.
  Future<List<OutboxEntry>> forScope(String scope) =>
      (_db.select(_db.outboxEntries)
            ..where((t) => t.scope.equals(scope))
            ..where((t) => t.status.isNotValue(OutboxStatus.done.name))
            ..orderBy([(t) => OrderingTerm.asc(t.createdAt)]))
          .get();

  Future<void> markInFlight(int id) => _update(
        id,
        OutboxEntriesCompanion(
          status: Value(OutboxStatus.inFlight.name),
          updatedAt: Value(DateTime.now()),
        ),
      );

  Future<void> markDone(int id) => _update(
        id,
        OutboxEntriesCompanion(
          status: Value(OutboxStatus.done.name),
          lastError: const Value(null),
          nextAttemptAt: const Value(null),
          updatedAt: Value(DateTime.now()),
        ),
      );

  /// Records a failed attempt and schedules the next one, or gives up.
  Future<OutboxStatus> markFailed(int id, String error) async {
    final entry = await byId(id);
    final attempts = (entry?.attemptCount ?? 0) + 1;
    final exhausted = attempts >= maxAttempts;

    await _update(
      id,
      OutboxEntriesCompanion(
        status: Value(
          exhausted ? OutboxStatus.deadLetter.name : OutboxStatus.pending.name,
        ),
        attemptCount: Value(attempts),
        lastError: Value(error),
        nextAttemptAt: Value(
          exhausted
              ? null
              : DateTime.now().add(
                  retryBackoff[
                      (attempts - 1).clamp(0, retryBackoff.length - 1)],
                ),
        ),
        updatedAt: Value(DateTime.now()),
      ),
    );

    return exhausted ? OutboxStatus.deadLetter : OutboxStatus.pending;
  }

  /// Gives up immediately, whatever the attempt count.
  ///
  /// For failures retrying provably cannot fix — a handler that threw a bug, or
  /// a kind this build no longer knows how to send. Spending eight attempts on
  /// a deterministic failure only delays telling the user about it.
  Future<void> deadLetter(int id, String error) => _update(
        id,
        OutboxEntriesCompanion(
          status: Value(OutboxStatus.deadLetter.name),
          lastError: Value(error),
          nextAttemptAt: const Value(null),
          updatedAt: Value(DateTime.now()),
        ),
      );

  /// Puts a given-up entry back in the queue at the user's request.
  Future<void> retryNow(int id) => _update(
        id,
        OutboxEntriesCompanion(
          status: Value(OutboxStatus.pending.name),
          attemptCount: const Value(0),
          lastError: const Value(null),
          nextAttemptAt: const Value(null),
          updatedAt: Value(DateTime.now()),
        ),
      );

  /// Abandons an entry the user has decided not to send.
  Future<void> discard(int id) =>
      (_db.delete(_db.outboxEntries)..where((t) => t.id.equals(id))).go();

  /// Clears delivered entries older than [olderThan].
  ///
  /// Done rows are kept for a while on purpose — "your change was sent" is only
  /// reassuring if it is still there when the user next looks.
  Future<int> pruneDelivered({Duration olderThan = const Duration(days: 3)}) {
    final cutoff = DateTime.now().subtract(olderThan);
    return (_db.delete(_db.outboxEntries)
          ..where((t) => t.status.equals(OutboxStatus.done.name))
          ..where((t) => t.updatedAt.isSmallerThanValue(cutoff)))
        .go();
  }

  /// Recovers entries left mid-flight by a crash or a kill.
  ///
  /// The app can be terminated between "mark in flight" and the response. On
  /// the next launch those rows would sit in inFlight forever, and the user's
  /// change would never be sent and never be reported as stuck.
  Future<int> requeueInterrupted() async {
    return (_db.update(_db.outboxEntries)
          ..where((t) => t.status.equals(OutboxStatus.inFlight.name)))
        .write(
      OutboxEntriesCompanion(
        status: Value(OutboxStatus.pending.name),
        updatedAt: Value(DateTime.now()),
      ),
    );
  }

  Future<OutboxEntry?> byId(int id) =>
      (_db.select(_db.outboxEntries)..where((t) => t.id.equals(id)))
          .getSingleOrNull();

  Future<void> _update(int id, OutboxEntriesCompanion values) async {
    await (_db.update(_db.outboxEntries)..where((t) => t.id.equals(id)))
        .write(values);
  }
}

/// Convenience accessors over the generated row class.
extension OutboxEntryX on OutboxEntry {
  OutboxStatus get parsedStatus => OutboxStatus.parse(status);

  Map<String, dynamic> get decodedPayload {
    final decoded = jsonDecode(payload);
    return decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
  }
}
