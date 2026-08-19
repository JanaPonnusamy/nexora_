import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/sync/data/sync_live_models.dart';

/// Client for the network-wide live sync operations.
///
/// Every path here was read off `backend/modules/sync/runtime_router.py` and
/// `backend/controllers/sync_admin_controller.py`. None of these endpoints are
/// tenant-scoped server-side, so callers must gate on `isPlatformUser` — the
/// same rule the existing `SyncAdminService` follows.
class SyncLiveService {
  const SyncLiveService(this._dio);

  final Dio _dio;

  /// In-flight executions across the network. Returns a bare array; an empty
  /// list means idle, not unreachable.
  Future<List<LiveSyncExecution>> fetchLive() async {
    try {
      final res = await _dio.get<List<dynamic>>(ApiEndpoints.syncLive);
      return (res.data ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(LiveSyncExecution.fromJson)
          .toList(growable: false);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Pauses or stops the running syncs for the given stores.
  ///
  /// The server applies this per store id in a loop, so a partial result is
  /// possible; [SyncControlResult.affected] is the count that actually
  /// changed, and the UI reports that number rather than assuming success.
  Future<SyncControlResult> control({
    required List<String> storeIds,
    required SyncControlAction action,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.syncControl,
        data: {'store_ids': storeIds, 'action': action.wire},
      );
      return SyncControlResult.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Queues a sync for one store. The store agent picks the task up on its
  /// next poll, so this returns as soon as the task row exists — the sync has
  /// been *asked for*, not performed.
  Future<String?> requestSync({
    required String tenantId,
    required String storeId,
    String executionType = 'FULL',
    String syncMode = 'FULL',
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.syncTaskCreate,
        data: {
          'tenant_id': tenantId,
          'store_id': storeId,
          'execution_type': executionType,
          'sync_mode': syncMode,
        },
      );
      return res.data?['task_id']?.toString();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Recent executions, newest first as the server orders them.
  Future<List<SyncHistoryEntry>> fetchHistory({
    String? storeId,
    String? status,
    int limit = 50,
  }) async {
    try {
      final res = await _dio.get<dynamic>(
        ApiEndpoints.syncHistory,
        queryParameters: {
          if (storeId != null) 'store_id': storeId,
          if (status != null) 'status': status,
          'limit': limit,
        },
      );
      // The endpoint has returned both a bare array and an object wrapping
      // one; accept either rather than showing an empty history on a shape
      // change that is not an error.
      final data = res.data;
      final rows = switch (data) {
        final List<dynamic> list => list,
        final Map<String, dynamic> map =>
          (map['history'] ?? map['executions'] ?? map['items']) as List? ??
              const [],
        _ => const [],
      };
      return rows
          .whereType<Map<String, dynamic>>()
          .map(SyncHistoryEntry.fromJson)
          .toList(growable: false);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
