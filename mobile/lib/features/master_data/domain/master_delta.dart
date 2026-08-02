/// A batch of changes for one master-data entity, as returned by the API layer
/// and applied by a repository.
///
/// The engine supports both incremental deltas (with explicit [deletedIds]) and
/// full snapshots (where absent rows are treated as deletions — see
/// [fullSnapshot]). Which one an entity uses depends on what its backend
/// endpoint provides; see docs/API_CONTRACT.md.
class MasterDelta {
  const MasterDelta({
    this.records = const [],
    this.deletedIds = const [],
    this.nextWatermark,
    this.fullSnapshot = false,
  });

  /// Raw record maps (decoded JSON) to upsert; parsed by each entity's DTO.
  final List<Map<String, dynamic>> records;

  /// Server-reported deletions (incremental mode only).
  final List<String> deletedIds;

  /// Cursor to persist for the next incremental pull, if the backend supports
  /// it. Null when the backend exposes no versioning/watermark.
  final String? nextWatermark;

  /// When true, [records] is the complete current set for the scope; the
  /// repository reconciles local rows not present here as soft-deleted.
  final bool fullSnapshot;

  bool get isEmpty => records.isEmpty && deletedIds.isEmpty;
  int get size => records.length + deletedIds.length;
}
