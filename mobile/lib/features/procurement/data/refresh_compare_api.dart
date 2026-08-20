import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/procurement/data/purchase_workspace_api.dart';
import 'package:nexora_mobile/features/procurement/domain/refresh_compare_models.dart';

class RefreshCompareApi {
  const RefreshCompareApi(this._dio, this._workspace);

  final Dio _dio;
  final PurchaseWorkspaceApi _workspace;
  static const _base = '/api/procurement';

  Future<List<ProcurementRefresh>> refreshes({
    required String tenantId,
    required String storeId,
  }) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        '$_base/vpl',
        queryParameters: {
          'tenant_id': tenantId,
          'store_id': storeId,
          'page': 1,
          'page_size': 200,
        },
      );
      return (response.data?['items'] as List? ?? const [])
          .whereType<Map>()
          .map(
              (row) => ProcurementRefresh.fromJson(row.cast<String, dynamic>()))
          .where((refresh) => refresh.refreshId.isNotEmpty)
          .toList(growable: false);
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<List<RefreshCompareRow>> compare({
    required String tenantId,
    required String sourceRefreshId,
    required String targetRefreshId,
  }) async {
    final pages = await Future.wait([
      _workspace.workspace(
        tenantId: tenantId,
        refreshId: sourceRefreshId,
      ),
      _workspace.workspace(
        tenantId: tenantId,
        refreshId: targetRefreshId,
      ),
    ]);
    return compareFinalOrders(pages[0].items, pages[1].items);
  }
}
