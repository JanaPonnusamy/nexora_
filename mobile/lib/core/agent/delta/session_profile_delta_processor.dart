import 'dart:convert';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/sync/delta_processor.dart';
import 'package:nexora_mobile/core/sync/sync_repository.dart';
import 'package:nexora_mobile/features/auth/data/auth_repository.dart';

/// Syncs the signed-in user's profile + module permissions (`GET /api/auth/me`)
/// into the local cache so entitlements are available offline. This is the
/// "metadata synchronization" entity.
class SessionProfileDeltaProcessor extends EntityDeltaProcessor {
  SessionProfileDeltaProcessor(this._auth, this._repo, this._isAuthenticated);

  final AuthRepository _auth;
  final SyncRepository _repo;
  final bool Function() _isAuthenticated;

  static const String entityName = 'user_profile';
  static const String configKey = 'user.profile';

  @override
  String get entity => entityName;

  @override
  Future<DeltaResult> pull({
    String? watermark,
    Map<String, dynamic> params = const {},
  }) async {
    if (!_isAuthenticated()) {
      return DeltaResult(entity: entity, changed: 0, recordCount: 0);
    }

    try {
      final user = await _auth.me();
      final existing = await _repo.getConfig(configKey);
      final version = (existing?.version ?? 0) + 1;
      await _repo.putConfig(
        configKey,
        jsonEncode(user.toJson()),
        version: version,
      );
      return DeltaResult(
        entity: entity,
        changed: 1,
        recordCount: 1,
        nextWatermark: DateTime.now().toIso8601String(),
      );
    } on ApiException catch (e) {
      // A 401 is handled globally (session teardown); treat as no-op here so the
      // queue doesn't dead-letter a benign auth expiry.
      if (e.statusCode == 401) {
        return DeltaResult(entity: entity, changed: 0, recordCount: 0);
      }
      rethrow;
    }
  }
}
