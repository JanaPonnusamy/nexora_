import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/master_data/domain/master_delta.dart';
import 'package:nexora_mobile/features/master_data/domain/master_scope.dart';

/// Network access for master-data entities.
///
/// A single shared service (not one class per entity) because most master
/// entities have no backend read endpoint yet — duplicating six near-empty
/// services would be dead code. Only [fetchSuppliers] is wired to a real
/// endpoint; the missing endpoints are documented in docs/API_CONTRACT.md and
/// their processors no-op rather than call an invented URL.
class MasterDataApiService {
  MasterDataApiService(this._dio);

  final Dio _dio;

  /// `GET /api/mobile/v1/suppliers?store_id=`
  ///
  /// Returns a FULL snapshot of suppliers that have imported stock for the
  /// store (with stock counts) — not the complete supplier master, and with no
  /// server-side delta/versioning. Absent rows are reconciled as deletions by
  /// the repository. Returns null when the scope is not store-resolved.
  ///
  /// Deliberately the BFF route rather than
  /// `/api/supplier-stock-analysis/suppliers`: that one is behind
  /// `require_admin_role`, which 403s purchase-manager and salesman logins —
  /// the exact field roles this app targets — leaving them with an empty
  /// supplier list and no explanation. The payload is identical, so nothing
  /// downstream of here changes. Tenant comes from the token, so it is not
  /// sent; `store_id` still is, because a user may hold more than one store
  /// and the sync is per selected store.
  Future<MasterDelta?> fetchSuppliers(
    MasterScope scope, {
    String? watermark,
  }) async {
    if (!scope.hasTenant || !scope.hasStore) return null;
    try {
      final res = await _dio.get<Map<String, dynamic>>(
        ApiEndpoints.mobileSuppliers,
        queryParameters: {'store_id': scope.storeId},
      );
      final data = res.data ?? const {};
      final rawList = data['suppliers'];
      final records = rawList is List
          ? rawList.whereType<Map<String, dynamic>>().toList(growable: false)
          : const <Map<String, dynamic>>[];
      return MasterDelta(
        records: records,
        fullSnapshot: true,
        nextWatermark: DateTime.now().toIso8601String(),
      );
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
