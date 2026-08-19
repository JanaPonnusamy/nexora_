import 'dart:async';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';

/// Applies one queued edit against the server.
///
/// Throws [ApiException] to signal failure; anything else is treated as a bug
/// in the handler and dead-letters immediately rather than retrying forever.
typedef OutboxHandler = Future<void> Function(Map<String, dynamic> payload);

/// What one drain pass did.
class OutboxDrainReport {
  const OutboxDrainReport({
    this.sent = 0,
    this.failed = 0,
    this.deadLettered = 0,
    this.skippedOffline = false,
  });

  final int sent;
  final int failed;
  final int deadLettered;

  /// True when the drain did nothing because the device has no network. Not a
  /// failure: nothing was attempted, so nothing should be reported as broken.
  final bool skippedOffline;

  bool get didWork => sent > 0 || failed > 0;
}

/// Drains the outbox.
///
/// Handlers are registered by the features that own each kind, so `core/` never
/// imports `features/` — the same reason the sync engine takes registered
/// entity processors rather than knowing about them.
class OutboxDispatcher {
  OutboxDispatcher({
    required OutboxRepository outbox,
    required ConnectivityService connectivity,
  })  : _outbox = outbox,
        _connectivity = connectivity;

  final OutboxRepository _outbox;
  final ConnectivityService _connectivity;
  final _log = AppLogger.of('Outbox');

  final Map<String, OutboxHandler> _handlers = {};
  bool _draining = false;

  void register(String kind, OutboxHandler handler) =>
      _handlers[kind] = handler;

  bool handles(String kind) => _handlers.containsKey(kind);

  /// Sends everything currently due.
  ///
  /// Safe to call often — a reconnect event and a manual retry arriving
  /// together collapse into the one pass already running, so an edit is never
  /// sent twice.
  Future<OutboxDrainReport> drain() async {
    if (_draining) return const OutboxDrainReport();

    // Claimed synchronously, before the first await. Setting it after the
    // connectivity check would leave a gap: both callers pass the guard, both
    // suspend on the check, and both proceed — which is how the same edit gets
    // sent twice and written to the audit trail twice.
    _draining = true;

    var sent = 0;
    var failed = 0;
    var deadLettered = 0;

    try {
      if (!await _connectivity.isOnline) {
        return const OutboxDrainReport(skippedOffline: true);
      }

      // Loop rather than one pass: `due()` yields at most one entry per scope
      // to keep ordering, so a document with three queued edits needs three
      // rounds. Stops as soon as a round achieves nothing, which is what keeps
      // a persistently failing entry from spinning.
      while (true) {
        final batch = await _outbox.due();
        if (batch.isEmpty) break;

        var progressed = false;
        for (final entry in batch) {
          final outcome = await _apply(entry);
          switch (outcome) {
            case _Outcome.sent:
              sent++;
              progressed = true;
            case _Outcome.failed:
              failed++;
            case _Outcome.deadLettered:
              deadLettered++;
              progressed = true; // the scope is unblocked, so keep going
          }
        }
        if (!progressed) break;
      }
    } finally {
      _draining = false;
    }

    if (sent > 0 || deadLettered > 0) {
      _log.info('Outbox drained: $sent sent, $failed failed, '
          '$deadLettered gave up');
    }
    return OutboxDrainReport(
      sent: sent,
      failed: failed,
      deadLettered: deadLettered,
    );
  }

  Future<_Outcome> _apply(OutboxEntry entry) async {
    final handler = _handlers[entry.kind];
    if (handler == null) {
      // A kind with no handler is a build that no longer knows how to send
      // something an older build queued. Retrying cannot help, and silently
      // dropping it would lose the user's edit — so it goes to the dead-letter
      // list where a person can see it.
      _log.severe('No handler registered for "${entry.kind}"');
      await _outbox.deadLetter(
        entry.id,
        'This version of the app cannot send that change.',
      );
      return _Outcome.deadLettered;
    }

    await _outbox.markInFlight(entry.id);
    try {
      await handler(entry.decodedPayload);
      await _outbox.markDone(entry.id);
      return _Outcome.sent;
    } on ApiException catch (e) {
      // An offline failure must not burn an attempt: the entry is no more
      // broken than it was a second ago, and counting it would march a
      // perfectly good edit towards the dead-letter list over a tunnel.
      if (e.isNetwork) {
        await _outbox.retryNow(entry.id);
        return _Outcome.failed;
      }
      final status = await _outbox.markFailed(entry.id, e.message);
      return status == OutboxStatus.deadLetter
          ? _Outcome.deadLettered
          : _Outcome.failed;
    } catch (e) {
      // Not an ApiException — a bug rather than a server refusal. Retrying a
      // deterministic crash just delays telling anyone about it.
      _log.severe('Handler for "${entry.kind}" threw: $e');
      await _outbox.deadLetter(entry.id, 'Unexpected error: $e');
      return _Outcome.deadLettered;
    }
  }
}

enum _Outcome { sent, failed, deadLettered }
