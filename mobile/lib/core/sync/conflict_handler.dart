/// Strategy for reconciling a local record with a diverging server record.
enum ConflictStrategy {
  /// Server value always wins (default for read-mostly config data).
  serverWins,

  /// Local value always wins.
  clientWins,

  /// Whichever carries the newer version / timestamp wins.
  lastWriteWins,
}

/// The decided outcome of a conflict.
enum ConflictResolution { takeServer, takeClient, noChange }

/// A pair of comparable revisions for one record. [version] is an optional
/// monotonic counter; [updatedAt] is the fallback tiebreaker.
class Revision {
  const Revision({this.version, this.updatedAt});
  final int? version;
  final DateTime? updatedAt;

  bool get isEmpty => version == null && updatedAt == null;
}

/// Detects and resolves conflicts between local and remote revisions. Pure and
/// deterministic so the delta processors and the merge path stay testable.
class ConflictHandler {
  const ConflictHandler({this.strategy = ConflictStrategy.serverWins});

  final ConflictStrategy strategy;

  /// True when the two revisions actually differ and a decision is needed.
  bool hasConflict(Revision local, Revision server) {
    if (local.isEmpty) return !server.isEmpty; // brand new server record
    if (server.isEmpty) return false;
    if (local.version != null && server.version != null) {
      return local.version != server.version;
    }
    if (local.updatedAt != null && server.updatedAt != null) {
      return !local.updatedAt!.isAtSameMomentAs(server.updatedAt!);
    }
    return true;
  }

  ConflictResolution resolve(Revision local, Revision server) {
    if (!hasConflict(local, server)) return ConflictResolution.noChange;

    switch (strategy) {
      case ConflictStrategy.serverWins:
        return ConflictResolution.takeServer;
      case ConflictStrategy.clientWins:
        return ConflictResolution.takeClient;
      case ConflictStrategy.lastWriteWins:
        return _newerWins(local, server);
    }
  }

  ConflictResolution _newerWins(Revision local, Revision server) {
    if (local.version != null && server.version != null) {
      return server.version! >= local.version!
          ? ConflictResolution.takeServer
          : ConflictResolution.takeClient;
    }
    if (local.updatedAt != null && server.updatedAt != null) {
      return !server.updatedAt!.isBefore(local.updatedAt!)
          ? ConflictResolution.takeServer
          : ConflictResolution.takeClient;
    }
    // Not enough information to compare → prefer the server copy.
    return ConflictResolution.takeServer;
  }
}
