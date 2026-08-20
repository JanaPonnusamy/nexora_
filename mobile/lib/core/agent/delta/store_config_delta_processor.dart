import 'package:nexora_mobile/core/agent/store_config_service.dart';
import 'package:nexora_mobile/core/sync/delta_processor.dart';

/// Syncs the active store's configuration (`GET /api/stores/{id}`) into the
/// local cache. This is the concrete "configuration download" entity registered
/// with the sync engine.
class StoreConfigDeltaProcessor extends EntityDeltaProcessor {
  StoreConfigDeltaProcessor(this._service, this._currentStoreId);

  final StoreConfigService _service;
  final String? Function() _currentStoreId;

  static const String entityName = 'store_config';

  @override
  String get entity => entityName;

  @override
  Future<DeltaResult> pull({
    String? watermark,
    Map<String, dynamic> params = const {},
  }) async {
    final storeId = _currentStoreId();
    if (storeId == null || storeId.isEmpty) {
      // No active store yet — nothing to pull, not an error.
      return DeltaResult(entity: entity, changed: 0, recordCount: 0);
    }

    final store = await _service.download(storeId);
    final present = store != null ? 1 : 0;
    return DeltaResult(
      entity: entity,
      changed: present,
      recordCount: present,
      nextWatermark: DateTime.now().toIso8601String(),
    );
  }
}
