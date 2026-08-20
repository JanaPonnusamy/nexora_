import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/procurement/domain/stock_distribution_models.dart';

class StockDistributionApi {
  const StockDistributionApi(this._dio);

  final Dio _dio;
  static const _base = '/api/procurement/distribution';

  Future<List<DistributionTarget>> config({
    required String tenantId,
    String sourceStoreCode = 'NMW',
  }) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '$_base/config',
        queryParameters: {
          'tenant_id': tenantId,
          'source_store_code': sourceStoreCode,
        },
      );
      return (response.data ?? const [])
          .whereType<Map>()
          .map(
              (row) => DistributionTarget.fromJson(row.cast<String, dynamic>()))
          .toList(growable: false);
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<List<DistributionRun>> runs({
    required String tenantId,
    int limit = 20,
  }) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '$_base/runs',
        queryParameters: {'tenant_id': tenantId, 'limit': limit},
      );
      return (response.data ?? const [])
          .whereType<Map>()
          .map((row) => DistributionRun.fromJson(row.cast<String, dynamic>()))
          .toList(growable: false);
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<DistributionRunDetail> detail(String runId) async {
    try {
      final response =
          await _dio.get<Map<String, dynamic>>('$_base/runs/$runId');
      return DistributionRunDetail.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<DistributionResult> generate({
    required String tenantId,
    required String sourceStoreCode,
    required String actor,
    List<String>? storeIds,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '$_base/generate',
        queryParameters: {
          'tenant_id': tenantId,
          'source_store_code': sourceStoreCode,
          'provider': 'legacy',
          if (storeIds != null) 'store_ids': storeIds.join(','),
          'started_by': actor,
        },
      );
      return DistributionResult.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }

  Future<DistributionResult> retry({
    required String runId,
    required String actor,
  }) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '$_base/runs/$runId/retry',
        queryParameters: {'provider': 'legacy', 'started_by': actor},
      );
      return DistributionResult.fromJson(response.data ?? const {});
    } on DioException catch (error) {
      throw ApiException.fromDio(error);
    }
  }
}
