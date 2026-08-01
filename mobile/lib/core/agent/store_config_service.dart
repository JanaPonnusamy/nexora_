import 'dart:convert';

import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/sync/conflict_handler.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';
import 'package:nexora_mobile/features/store_selection/data/models/store.dart';
import 'package:nexora_mobile/features/store_selection/data/store_repository.dart';

/// A cached store configuration plus the time it was fetched.
class CachedStoreConfig {
  const CachedStoreConfig(
      {required this.store, required this.fetchedAt, required this.version,});
  final Store store;
  final DateTime fetchedAt;
  final int version;
}

/// Downloads and caches the store configuration.
///
/// Per the confirmed design, the mobile client caches ONLY the plain store
/// record from `GET /api/stores/{id}` — it never pulls the desktop agent's
/// `/agent-config` (which carries encrypted DB credentials). The cached copy is
/// what makes configuration available fully offline and across restarts.
class StoreConfigService {
  StoreConfigService(
    this._stores,
    this._repo, {
    ConflictHandler conflictHandler = const ConflictHandler(),
  }) : _conflict = conflictHandler;

  static const String configKey = 'store.config';

  final StoreRepository _stores;
  final SyncRepository _repo;
  final ConflictHandler _conflict;
  final _log = AppLogger.of('StoreConfig');

  /// Fetches the live store record and refreshes the cache. Returns the fetched
  /// store, or `null` if the backend reports the store does not exist.
  Future<Store?> download(String storeId) async {
    final store = await _stores.getById(storeId);
    if (store == null) {
      _log.warning('Store $storeId not found on backend');
      return null;
    }
    await _cache(store);
    _log.info('Downloaded config for store ${store.storeCode}');
    return store;
  }

  Future<void> _cache(Store store) async {
    final existing = await _repo.getConfig(configKey);
    final newJson = jsonEncode(store.toJson());

    if (existing != null) {
      // Identical payload → nothing to do (avoids version churn + needless
      // stream emissions to the UI).
      if (existing.value == newJson) {
        _log.fine('Store config unchanged (v${existing.version})');
        return;
      }
      // A differing payload is a conflict; the resolution strategy decides
      // whether the fresh download supersedes the cached copy. Server metadata
      // (updatedAt/version) is not exposed by the backend yet, so the default
      // serverWins strategy applies — see docs/API_CONTRACT.md.
      final decision = _conflict.resolve(
        Revision(version: existing.version, updatedAt: existing.updatedAt),
        Revision(version: existing.version + 1, updatedAt: DateTime.now()),
      );
      if (decision == ConflictResolution.takeClient) {
        _log.info('Kept cached store config over download (conflict)');
        return;
      }
    }

    final version = (existing?.version ?? 0) + 1;
    await _repo.putConfig(configKey, newJson, version: version);
  }

  /// Reads the cached configuration without any network access.
  Future<CachedStoreConfig?> readCached() async {
    final row = await _repo.getConfig(configKey);
    if (row == null) return null;
    try {
      final store =
          Store.fromJson(jsonDecode(row.value) as Map<String, dynamic>);
      return CachedStoreConfig(
        store: store,
        fetchedAt: row.updatedAt,
        version: row.version,
      );
    } catch (e) {
      _log.warning('Corrupt cached store config: $e');
      return null;
    }
  }

  /// Reactive view of the cached configuration for the UI.
  Stream<CachedStoreConfig?> watchCached() =>
      _repo.watchConfig(configKey).map((row) {
        if (row == null) return null;
        try {
          final store =
              Store.fromJson(jsonDecode(row.value) as Map<String, dynamic>);
          return CachedStoreConfig(
            store: store,
            fetchedAt: row.updatedAt,
            version: row.version,
          );
        } catch (_) {
          return null;
        }
      });
}
