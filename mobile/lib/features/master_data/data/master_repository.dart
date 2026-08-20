import 'package:nexora_mobile/features/master_data/domain/master_delta.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';

/// The write surface every master-data repository exposes to the sync engine.
/// The delta processor depends only on this — it never needs the typed read
/// methods, keeping the engine decoupled from each entity's shape.
///
/// Repositories are Drift-only: they NEVER touch the network. Sync writes here;
/// the UI reads here. That is what makes the app fully functional offline.
abstract class MasterWriter {
  /// Applies a batch of upserts/deletes for [scope]. Conflicts are resolved via
  /// the shared ConflictHandler. Returns the number of rows changed.
  Future<int> applyDelta(MasterDelta delta, MasterScope scope);

  /// Count of live (non-deleted) rows in [scope].
  Future<int> count(MasterScope scope);
}
