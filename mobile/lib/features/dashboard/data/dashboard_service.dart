import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/dashboard/data/dashboard_summary.dart';

/// Reads the Home tab aggregate from the mobile BFF.
///
/// One call replaces the several the phone would otherwise make on every app
/// open. Tenant scoping is resolved server-side from the JWT, so unlike most of
/// this API no `tenant_id` query parameter is passed.
class DashboardService {
  const DashboardService(this._dio);

  final Dio _dio;

  Future<DashboardSummary> fetch({String? storeId}) async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.mobileDashboard,
        queryParameters: {if (storeId != null) 'store_id': storeId},
      );
      return DashboardSummary.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
