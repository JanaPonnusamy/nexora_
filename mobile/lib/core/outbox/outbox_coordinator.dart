import 'dart:async';

import 'package:nexora_mobile/core/outbox/outbox_dispatcher.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/connectivity_service.dart';

/// Decides *when* the outbox drains.
///
/// Three triggers, because no one of them is enough on its own:
///
///  * **On start** — recovers anything a previous run left owing, and requeues
///    entries stranded mid-flight by a kill.
///  * **On reconnect** — the one that matters. Edits made in a stockroom go out
///    the moment there is signal, without the user opening anything.
///  * **On a slow timer** — covers a server that was down while the device was
///    online the whole time, which no connectivity event will ever announce.
///
/// The timer is deliberately lazy and stops when the outbox empties, so an app
/// left open on a counter is not waking to do nothing every minute.
class OutboxCoordinator {
  OutboxCoordinator({
    required OutboxRepository outbox,
    required OutboxDispatcher dispatcher,
    required ConnectivityService connectivity,
    Duration sweepInterval = const Duration(minutes: 5),
  })  : _outbox = outbox,
        _dispatcher = dispatcher,
        _connectivity = connectivity,
        _sweepInterval = sweepInterval;

  final OutboxRepository _outbox;
  final OutboxDispatcher _dispatcher;
  final ConnectivityService _connectivity;
  final Duration _sweepInterval;
  final _log = AppLogger.of('Outbox');

  StreamSubscription<NetworkStatus>? _connSub;
  Timer? _sweep;
  bool _started = false;

  /// Idempotent — a re-login must not attach a second listener.
  Future<void> start() async {
    if (_started) return;
    _started = true;

    // Anything the app was mid-send on when it was killed is owed again. The
    // server may or may not have applied it; re-sending a patch of the same
    // fields to the same values is harmless, losing the edit is not.
    final recovered = await _outbox.requeueInterrupted();
    if (recovered > 0) {
      _log.info(
          'Requeued $recovered interrupted change(s) from a previous run');
    }

    _connSub ??= _connectivity.statusStream.listen((status) {
      if (status.isOnline) unawaited(drainNow());
    });

    unawaited(drainNow());
  }

  /// Drains, then keeps a timer alive only while work remains.
  Future<OutboxDrainReport> drainNow() async {
    final report = await _dispatcher.drain();
    await _rescheduleSweep();
    return report;
  }

  Future<void> _rescheduleSweep() async {
    final outstanding = await _outbox.outstanding();
    // Dead-lettered entries are excluded: they need a person, and a timer
    // cannot supply one. Leaving the timer running for them would mean an app
    // that never goes quiet.
    final actionable = outstanding
        .where((e) => e.parsedStatus != OutboxStatus.deadLetter)
        .isNotEmpty;

    if (!actionable) {
      _sweep?.cancel();
      _sweep = null;
      return;
    }
    _sweep ??= Timer.periodic(_sweepInterval, (_) => unawaited(drainNow()));
  }

  void dispose() {
    _connSub?.cancel();
    _connSub = null;
    _sweep?.cancel();
    _sweep = null;
    _started = false;
  }
}
