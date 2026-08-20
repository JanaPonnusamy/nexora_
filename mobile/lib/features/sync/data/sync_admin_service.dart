import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/sync/data/sync_control_center.dart';

/// Read-only access to the network-wide sync administration data — the same
/// `GET /api/sync/control-center` endpoint the HO web console's Sync Control
/// Center dashboard consumes. Nothing here is written to; this service only
/// surfaces platform status for the mobile "Network" overview.
///
/// The endpoint is not tenant-scoped server-side, so callers must gate
/// visibility to platform users on the client (see `sync_admin_providers.dart`).
class SyncAdminService {
  SyncAdminService(this._dio);

  final Dio _dio;

  Future<SyncControlCenter> fetchControlCenter() async {
    try {
      final res =
          await _dio.get<Map<String, dynamic>>(ApiEndpoints.syncControlCenter);
      return SyncControlCenter.fromJson(res.data ?? const {});
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
