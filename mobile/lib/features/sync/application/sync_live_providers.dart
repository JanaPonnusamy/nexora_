import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/sync/data/sync_live_models.dart';
import 'package:nexora_mobile/features/sync/data/sync_live_service.dart';

/// Live sync is **online-only** by design (see the plan's offline matrix): a
/// stale picture of which stores are syncing right now is worse than an honest
/// empty state, so nothing here is cached to Drift.

final syncLiveServiceProvider = Provider<SyncLiveService>(
  (ref) => SyncLiveService(ref.watch(dioProvider)),
);

/// How often the live grid re-polls while someone is looking at it.
///
/// The agents report per-table progress every few seconds, so anything tighter
/// than this shows the same numbers twice and costs a round trip over
/// whatever connection the phone happens to be on.
const Duration syncLivePollInterval = Duration(seconds: 5);

/// In-flight executions, re-polled on a timer.
///
/// `autoDispose` is what makes the polling safe: the timer is created when the
/// screen starts watching and cancelled the moment it stops, so the app is not
/// hitting the HO server every five seconds from a backgrounded tab.
final syncLiveProvider =
    StreamProvider.autoDispose<List<LiveSyncExecution>>((ref) {
  final service = ref.watch(syncLiveServiceProvider);
  final controller = StreamController<List<LiveSyncExecution>>();
  Timer? timer;
  var closed = false;
  var hasEmitted = false;

  Future<void> poll() async {
    if (closed) return;
    try {
      final live = await service.fetchLive();
      if (closed) return;
      hasEmitted = true;
      controller.add(live);
    } on Object catch (e, st) {
      if (closed) return;
      // Surface the *first* failure, so a screen that cannot reach the server
      // says so instead of looking idle. After that, keep the last good frame:
      // one dropped packet on a five-second poll should not blank the grid.
      if (!hasEmitted) controller.addError(e, st);
    }
  }

  unawaited(poll());
  timer = Timer.periodic(syncLivePollInterval, (_) => unawaited(poll()));

  ref.onDispose(() {
    closed = true;
    timer?.cancel();
    controller.close();
  });

  return controller.stream;
});

/// Recent executions. Not polled — history only changes when something
/// finishes, and the live grid is already telling you that.
final syncHistoryProvider =
    FutureProvider.autoDispose.family<List<SyncHistoryEntry>, String?>(
  (ref, storeId) =>
      ref.watch(syncLiveServiceProvider).fetchHistory(storeId: storeId),
);
