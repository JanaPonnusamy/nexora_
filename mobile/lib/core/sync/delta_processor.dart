import 'dart:convert';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/sync/sync_logger.dart';
import 'package:nexora_mobile/core/sync/sync_queue.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';

/// Outcome of processing one delta operation.
class DeltaResult {
  const DeltaResult({
    required this.entity,
    this.changed = 0,
    this.recordCount = 0,
    this.nextWatermark,
  });

  final String entity;

  /// Number of records inserted/updated/deleted locally this run.
  final int changed;

  /// Total records now held for the entity (for reporting).
  final int recordCount;

  /// Server cursor to persist for the next incremental pull.
  final String? nextWatermark;
}

/// Contract each syncable entity implements. Concrete processors that hit the
/// backend live in the feature/agent layer; the engine only knows this
/// interface, keeping `core/sync` free of endpoint knowledge.
abstract class EntityDeltaProcessor {
  /// Logical entity name; must match the queue row's `entity`.
  String get entity;

  /// Pulls the latest delta from the backend using [watermark] as the cursor
  /// and persists it locally. [params] carries operation-specific arguments
  /// (decoded from the queue row's payload).
  Future<DeltaResult> pull({
    String? watermark,
    Map<String, dynamic> params = const {},
  });

  /// Pushes a locally-queued mutation. Read-mostly entities may leave this
  /// unimplemented; the engine dead-letters an unsupported upload cleanly.
  Future<DeltaResult> push(SyncQueueData item) {
    throw UnsupportedError('Uploads are not supported for "$entity"');
  }
}

/// Dispatches queued operations to the registered [EntityDeltaProcessor]s and
/// keeps `sync_metadata` (watermark, counts, status) current after each run.
class DeltaProcessor {
  DeltaProcessor(this._repo, this._logger);

  final SyncRepository _repo;
  final SyncLogger _logger;
  final Map<String, EntityDeltaProcessor> _processors = {};

  void register(EntityDeltaProcessor processor) {
    _processors[processor.entity] = processor;
  }

  void registerAll(Iterable<EntityDeltaProcessor> processors) {
    for (final p in processors) {
      register(p);
    }
  }

  Iterable<String> get entities => _processors.keys;

  bool supports(String entity) => _processors.containsKey(entity);

  /// Runs one queue item end-to-end: resolves the processor, executes the
  /// pull/push, then advances the entity's metadata. Throws on failure so the
  /// [SyncQueue] can apply its retry policy.
  Future<DeltaResult> process(SyncQueueData item) async {
    final processor = _processors[item.entity];
    if (processor == null) {
      throw StateError('No delta processor registered for "${item.entity}"');
    }

    final meta = await _repo.getMetadata(item.entity);
    final DeltaResult result;

    if (item.direction == SyncDirection.download.name) {
      result = await processor.pull(
        watermark: meta?.watermark,
        params: _decodePayload(item.payload),
      );
    } else {
      result = await processor.push(item);
    }

    await _repo.upsertMetadata(
      entity: item.entity,
      watermark: result.nextWatermark,
      lastSyncAt: DateTime.now(),
      lastStatus: 'success',
      recordCount: result.recordCount,
    );
    await _logger.info(
      '${item.direction} ${item.entity}: ${result.changed} changed',
      category: 'delta',
      entity: item.entity,
    );
    return result;
  }

  /// Marks an entity's metadata as failed (called by the manager after retries
  /// are exhausted) without throwing.
  Future<void> markFailed(String entity, Object error) => _repo.upsertMetadata(
        entity: entity,
        lastStatus: 'failed',
      );

  Map<String, dynamic> _decodePayload(String raw) {
    if (raw.trim().isEmpty) return const {};
    try {
      final decoded = jsonDecode(raw);
      return decoded is Map<String, dynamic> ? decoded : const {};
    } on FormatException {
      return const {};
    }
  }
}
