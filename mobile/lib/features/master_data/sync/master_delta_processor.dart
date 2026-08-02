import 'package:nexora_mobile/core/sync/delta_processor.dart';
import 'package:nexora_mobile/core/sync/sync_logger.dart';
import 'package:nexora_mobile/features/master_data/data/master_repository.dart';
import 'package:nexora_mobile/features/master_data/domain/master_delta.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';

/// Fetches a delta for an entity within [scope]. Null return means "nothing to
/// apply" (e.g. scope not ready, or no backend endpoint).
typedef MasterFetch = Future<MasterDelta?> Function(
  MasterScope scope, {
  String? watermark,
});

/// Generic bridge between the Phase-3 sync engine and a master-data repository.
///
/// It plugs into the existing [EntityDeltaProcessor] contract (registered with
/// SyncManager, driven by the queue, retried, restart-recovered — all unchanged)
/// and adds nothing to `core/sync`. Concrete per-entity processors subclass this
/// and supply their entity name, repository writer and fetch function.
///
/// When [fetch] is null the entity has no backend endpoint yet (documented in
/// docs/API_CONTRACT.md): the processor cleanly no-ops instead of calling an
/// invented URL, so the app keeps working offline on whatever is cached.
class MasterDeltaProcessor extends EntityDeltaProcessor {
  MasterDeltaProcessor({
    required String entity,
    required MasterWriter writer,
    required MasterScope Function() scope,
    MasterFetch? fetch,
    bool storeScoped = false,
    SyncLogger? logger,
  })  : _entity = entity,
        _writer = writer,
        _scope = scope,
        _fetch = fetch,
        _storeScoped = storeScoped,
        _logger = logger;

  final String _entity;
  final MasterWriter _writer;
  final MasterScope Function() _scope;
  final MasterFetch? _fetch;
  final bool _storeScoped;
  final SyncLogger? _logger;

  @override
  String get entity => _entity;

  @override
  Future<DeltaResult> pull({
    String? watermark,
    Map<String, dynamic> params = const {},
  }) async {
    final scope = _scope();

    // No tenant/store yet → not an error; leave cached data untouched.
    if (!scope.hasTenant || (_storeScoped && !scope.hasStore)) {
      return DeltaResult(entity: entity, changed: 0, recordCount: 0);
    }

    // No backend endpoint (documented gap) → no-op, keep cache.
    if (_fetch == null) {
      final total = await _writer.count(scope);
      await _logger?.info(
        'No backend endpoint for "$entity" yet — using cached data',
        category: 'delta',
        entity: entity,
      );
      return DeltaResult(entity: entity, changed: 0, recordCount: total);
    }

    final delta = await _fetch(scope, watermark: watermark);
    if (delta == null) {
      final total = await _writer.count(scope);
      return DeltaResult(entity: entity, changed: 0, recordCount: total);
    }

    final changed = await _writer.applyDelta(delta, scope);
    final total = await _writer.count(scope);
    return DeltaResult(
      entity: entity,
      changed: changed,
      recordCount: total,
      // Preserve the existing watermark when the backend exposes none.
      nextWatermark: delta.nextWatermark ?? watermark,
    );
  }
}
