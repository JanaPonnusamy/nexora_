import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/pass_gen/domain/pass_gen_models.dart';

/// Client for `/api/pass-gen/*`.
///
/// Every endpoint here 403s for anyone without unrestricted scope, so the
/// screen is gated on `isPlatformUser` before it is ever reachable. The client
/// still surfaces the 403 rather than swallowing it — a platform user whose
/// role changed mid-session needs to be told, not shown an empty list.
class PassGenApi {
  const PassGenApi(this._dio);

  final Dio _dio;

  static const String _base = '/api/pass-gen';

  /// Active stores and their numeric codes, optionally narrowed to a tenant.
  Future<List<PassGenStore>> stores({String? tenantId}) async {
    try {
      final res = await _dio.get<List<dynamic>>(
        '$_base/stores',
        queryParameters: {if (tenantId != null) 'tenant_id': tenantId},
      );
      return (res.data ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(PassGenStore.fromJson)
          .toList(growable: false);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Maps a store to its two-digit code, or clears it with null.
  ///
  /// Returns the **whole** store list, which is why the caller can replace its
  /// state wholesale rather than patching one row.
  Future<List<PassGenStore>> setStoreCode(String storeId, int? code) async {
    try {
      final res = await _dio.put<List<dynamic>>(
        '$_base/stores/$storeId/code',
        data: {'numeric_code': code},
      );
      return (res.data ?? const [])
          .whereType<Map<String, dynamic>>()
          .map(PassGenStore.fromJson)
          .toList(growable: false);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// Generates passcodes. The response carries one entry per request row;
  /// mobile sends a single row, so callers take the first.
  Future<PassGenRowResult> generate(PassGenRequest request) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        '$_base/generate',
        data: request.toJson(),
      );
      final rows = res.data?['rows'];
      if (rows is! List || rows.isEmpty) {
        return const PassGenRowResult(rowId: 'mobile');
      }
      return PassGenRowResult.fromJson(
        rows.first as Map<String, dynamic>,
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
