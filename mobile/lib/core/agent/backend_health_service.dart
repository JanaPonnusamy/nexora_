import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';

/// Result of a single backend health probe.
class HealthResult {
  const HealthResult({
    required this.reachable,
    required this.checkedAt,
    this.latencyMs,
    this.statusText,
    this.serverApiVersion,
    this.apiCompatible = false,
    this.error,
  });

  final bool reachable;
  final DateTime checkedAt;
  final int? latencyMs;
  final String? statusText;
  final String? serverApiVersion;
  final bool apiCompatible;
  final String? error;

  HealthResult.unreachable(Object error)
      : reachable = false,
        checkedAt = DateTime.now(),
        latencyMs = null,
        statusText = null,
        serverApiVersion = null,
        apiCompatible = false,
        error = error.toString();
}

/// Probes backend reachability (`GET /health`) and evaluates API-version
/// compatibility.
///
/// NOTE: the current `/health` endpoint returns only `{"status":"healthy"}` —
/// it exposes no version field or header. Until a versioned health/handshake
/// endpoint is added server-side (documented in docs/API_CONTRACT.md), a
/// reachable, healthy backend is treated as compatible; if a version ever
/// appears (`version`/`api_version` body key or `X-API-Version` header) it is
/// compared against [clientApiVersion].
class BackendHealthService {
  BackendHealthService(this._dio);

  final Dio _dio;
  final _log = AppLogger.of('Health');

  /// The API contract version this client build targets. Bump when a breaking
  /// backend change requires a coordinated release.
  static const String clientApiVersion = '1';

  Future<HealthResult> check() async {
    final started = DateTime.now();
    try {
      final res = await _dio.get<dynamic>(
        ApiEndpoints.health,
        options: Options(
          extra: const {'requiresAuth': false},
          receiveTimeout: const Duration(seconds: 8),
        ),
      );
      final latency = DateTime.now().difference(started).inMilliseconds;

      final body = res.data;
      final status = body is Map ? body['status']?.toString() : null;
      final serverVersion = _extractVersion(res);
      final compatible = _isCompatible(serverVersion);

      _log.fine('Health OK (${latency}ms, status=$status)');
      return HealthResult(
        reachable: true,
        checkedAt: started,
        latencyMs: latency,
        statusText: status ?? 'healthy',
        serverApiVersion: serverVersion,
        apiCompatible: compatible,
      );
    } on DioException catch (e) {
      _log.warning('Health probe failed: ${e.message}');
      return HealthResult.unreachable(e.message ?? e);
    }
  }

  String? _extractVersion(Response<dynamic> res) {
    final header = res.headers.value('x-api-version');
    if (header != null && header.isNotEmpty) return header;
    final body = res.data;
    if (body is Map) {
      final v = body['api_version'] ?? body['version'];
      if (v != null) return v.toString();
    }
    return null;
  }

  /// Compatible when the server does not advertise a version (best-effort), or
  /// when its major version matches the client's.
  bool _isCompatible(String? serverVersion) {
    if (serverVersion == null || serverVersion.isEmpty) return true;
    final serverMajor = serverVersion.split('.').first;
    final clientMajor = clientApiVersion.split('.').first;
    return serverMajor == clientMajor;
  }
}
