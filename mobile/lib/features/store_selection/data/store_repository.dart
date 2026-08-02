import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/store_selection/data/models/store.dart';

/// Data access for stores. Consumes the existing `/api/stores` endpoints.
///
/// For a store-scoped user the store list comes from their roles (already in
/// the login payload); this repository is used for platform users and to
/// resolve a store's full record.
class StoreRepository {
  StoreRepository(this._dio);

  final Dio _dio;

  /// `GET /api/stores` — all stores (platform scope).
  Future<List<Store>> getAll() async {
    try {
      final res = await _dio.get<List<dynamic>>(ApiEndpoints.stores);
      return (res.data ?? [])
          .whereType<Map<String, dynamic>>()
          .map(Store.fromJson)
          .toList();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// `GET /api/stores/{store_id}` — full record for one store.
  ///
  /// The backend returns `{"error": "Store Not Found"}` (HTTP 200) for an
  /// unknown id rather than a 404, so that shape is treated as "not found".
  Future<Store?> getById(String storeId) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.store(storeId),
      );
      final data = res.data;
      if (data == null || data.containsKey('error')) return null;
      return Store.fromJson(data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// `GET /api/stores/tenant/{tenant_id}` — stores for one tenant (slim shape).
  Future<List<Store>> getByTenant(String tenantId) async {
    try {
      final res = await _dio.get<List<dynamic>>(
        ApiEndpoints.storesByTenant(tenantId),
      );
      return (res.data ?? [])
          .whereType<Map<String, dynamic>>()
          .map(Store.fromJson)
          .toList();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
