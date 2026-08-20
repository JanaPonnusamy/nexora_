import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/outbox/outbox_coordinator.dart';
import 'package:nexora_mobile/core/outbox/outbox_dispatcher.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';

/// Phase 3 — the offline outbox.
///
/// Separate from `providers.dart` for the same reason the capture graph is:
/// nothing here should be constructed just because a screen wanted a Dio.

final outboxRepositoryProvider = Provider<OutboxRepository>(
  (ref) => OutboxRepository(ref.watch(appDatabaseProvider)),
);

/// Handlers are registered onto this by the features that own each kind — see
/// `capture_providers.dart` for the document-extraction ones.
final outboxDispatcherProvider = Provider<OutboxDispatcher>(
  (ref) => OutboxDispatcher(
    outbox: ref.watch(outboxRepositoryProvider),
    connectivity: ref.watch(connectivityServiceProvider),
  ),
);

final outboxCoordinatorProvider = Provider<OutboxCoordinator>((ref) {
  final coordinator = OutboxCoordinator(
    outbox: ref.watch(outboxRepositoryProvider),
    dispatcher: ref.watch(outboxDispatcherProvider),
    connectivity: ref.watch(connectivityServiceProvider),
  );
  ref.onDispose(coordinator.dispose);
  return coordinator;
});

/// Live view of everything still owed to the server. Backs the pending-changes
/// surfaces; a count of zero is what tells a user it is safe to close the app.
final outboxOutstandingProvider = StreamProvider<List<OutboxEntry>>(
  (ref) => ref.watch(outboxRepositoryProvider).watchOutstanding(),
);
