import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/procurement/domain/cycle_models.dart';

/// Typed client for the procurement cycle and refresh lifecycle.
///
/// Every path and parameter was read off `modules/procurement/router.py` and
/// `orchestration_router.py`; nothing is invented. Note the module is
/// tenant-scoped by query parameter, like document extraction and unlike the
/// mobile BFF.
class CycleApi {
  const CycleApi(this._dio);

  final Dio _dio;

  static const String _base = '/api/procurement';

  Future<CyclePage> cycles({
    required String tenantId,
    String? storeId,
    String? status,
    String? search,
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/cycles',
        queryParameters: {
          'tenant_id': tenantId,
          if (storeId != null) 'store_id': storeId,
          if (status != null) 'status': status,
          if (search != null && search.isNotEmpty) 'search': search,
          'page': page,
          'page_size': pageSize,
        },
      );
      return CyclePage.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<ProcurementCycle> cycle({
    required String tenantId,
    required String cycleId,
  }) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        '$_base/cycles/$cycleId',
        queryParameters: {'tenant_id': tenantId},
      );
      return ProcurementCycle.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Starts the next refresh in an open cycle.
  ///
  /// The server runs the engine and generates working items synchronously, so
  /// this call is slow by nature — the console shows progress rather than a
  /// spinner that looks hung.
  Future<Map<String, dynamic>> createRefresh({
    required String tenantId,
    required String cycleId,
    required Map<String, dynamic> payload,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '$_base/cycles/$cycleId/refreshes',
        queryParameters: {'tenant_id': tenantId},
        data: payload,
      );
      return res.data ?? const {};
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Locks a refresh read-only without closing its cycle.
  Future<CloseOutcome> closeRefresh({
    required String tenantId,
    required String refreshId,
    required String closedBy,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '$_base/refreshes/$refreshId/close',
        queryParameters: {'tenant_id': tenantId},
        data: {'closed_by': closedBy},
      );
      return CloseOutcome.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Reconciles and closes a cycle, auto-opening a fresh one.
  ///
  /// Returns `status='pending_confirm'` when items remain and [force] was not
  /// set. That is the server asking a question, and the caller must surface it
  /// rather than silently retrying with force — closing over unresolved items
  /// is a decision, not a retry.
  Future<CloseOutcome> closeCycle({
    required String tenantId,
    required String cycleId,
    required String closedBy,
    bool force = false,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '$_base/cycles/$cycleId/close',
        queryParameters: {'tenant_id': tenantId},
        data: {'closed_by': closedBy, 'force': force},
      );
      return CloseOutcome.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
