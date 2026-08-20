import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/procurement/domain/purchase_workspace_models.dart';

class PurchaseWorkspaceApi {
  const PurchaseWorkspaceApi(this._dio);

  final Dio _dio;
  static const _base = '/api/procurement';

  Future<PurchaseWorkspacePage> workspace({
    required String tenantId,
    required String refreshId,
    String? search,
    int page = 1,
    int pageSize = 5000,
  }) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '$_base/refreshes/$refreshId/workspace',
        queryParameters: {
          'tenant_id': tenantId,
          if (search != null && search.trim().isNotEmpty)
            'search': search.trim(),
          'page': page,
          'page_size': pageSize,
        },
      );
      return PurchaseWorkspacePage.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<PurchaseWorkspaceItem> item({
    required String tenantId,
    required String orderItemId,
  }) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '$_base/order-items/$orderItemId',
        queryParameters: {'tenant_id': tenantId},
      );
      return PurchaseWorkspaceItem.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<PurchaseWorkspaceItem> setFinalQty({
    required String tenantId,
    required String orderItemId,
    required double finalQty,
    String? actor,
  }) async {
    try {
      final response = await _dio.put<Map<String, dynamic>>(
        '$_base/order-items/$orderItemId/final-qty',
        queryParameters: {'tenant_id': tenantId},
        data: {'final_qty': finalQty, 'reviewed_by': actor},
      );
      return PurchaseWorkspaceItem.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<List<PurchaseSupplier>> suppliers({
    required String tenantId,
    required String storeId,
    required String query,
  }) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '$_base/suppliers/search',
        queryParameters: {
          'tenant_id': tenantId,
          'store_id': storeId,
          'q': query.trim(),
          'limit': 20,
        },
      );
      return (response.data?['suppliers'] as List? ?? const [])
          .whereType<Map>()
          .map((row) => PurchaseSupplier.fromJson(row.cast<String, dynamic>()))
          .where((supplier) => supplier.code.isNotEmpty)
          .toList(growable: false);
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<PurchaseWorkspaceItem> assign({
    required String tenantId,
    required String orderItemId,
    required String supplierCode,
    required double qty,
    String? actor,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '$_base/order-items/$orderItemId/assignments',
        queryParameters: {'tenant_id': tenantId},
        data: {
          'supplier_code': supplierCode,
          'qty': qty,
          'created_by': actor,
        },
      );
      final item = response.data?['item'];
      return PurchaseWorkspaceItem.fromJson(
        item is Map ? item.cast<String, dynamic>() : const {},
      );
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<PurchaseWorkspaceItem> skip({
    required String tenantId,
    required String orderItemId,
    required String reason,
    String? actor,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '$_base/order-items/$orderItemId/skip',
        queryParameters: {'tenant_id': tenantId},
        data: {'skip_reason': reason, 'reviewed_by': actor},
      );
      return PurchaseWorkspaceItem.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<PurchaseWorkspaceItem> restore({
    required String tenantId,
    required String orderItemId,
    String? actor,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '$_base/order-items/$orderItemId/restore',
        queryParameters: {'tenant_id': tenantId},
        data: {'reviewed_by': actor},
      );
      return PurchaseWorkspaceItem.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }
}
