import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';

/// Outcome of a refresh attempt.
enum RefreshOutcome {
  /// A new access token was stored; the caller may retry its request.
  refreshed,

  /// No refresh token available — the session was never upgraded, or logout
  /// already cleared it.
  unavailable,

  /// The server rejected the refresh token. The session is over.
  rejected,

  /// Network/transport failure. The existing tokens are still presumed valid,
  /// so the session is NOT torn down.
  transient,
}

/// Exchanges a refresh token for a fresh access token against the mobile BFF.
///
/// Refresh tokens are single-use and rotated server-side, and presenting an
/// already-rotated token is treated as theft — the server revokes every token
/// for the device. Two parallel refreshes would therefore log the user out, so
/// attempts are single-flighted: concurrent callers await one shared future.
class TokenRefresher {
  TokenRefresher({
    required SecureStorageService storage,
    required String baseUrl,
    Dio? httpClient,
  })  : _storage = storage,
        // A bare Dio deliberately: reusing the app's instance would send this
        // request back through AuthInterceptor and recurse on its own 401.
        _dio = httpClient ??
            Dio(
              BaseOptions(
                baseUrl: baseUrl,
                connectTimeout: const Duration(seconds: 15),
                receiveTimeout: const Duration(seconds: 20),
              ),
            );

  final SecureStorageService _storage;
  final Dio _dio;
  final _log = AppLogger.of('TokenRefresher');

  Future<RefreshOutcome>? _inFlight;

  /// Attempts a refresh, coalescing concurrent callers into one request.
  Future<RefreshOutcome> refresh() {
    final existing = _inFlight;
    if (existing != null) {
      _log.fine('Joining in-flight refresh');
      return existing;
    }
    final attempt = _refresh().whenComplete(() => _inFlight = null);
    _inFlight = attempt;
    return attempt;
  }

  Future<RefreshOutcome> _refresh() async {
    final refreshToken = await _storage.readRefreshToken();
    final deviceId = await _storage.readDeviceId();

    if (refreshToken == null || refreshToken.isEmpty || deviceId == null) {
      return RefreshOutcome.unavailable;
    }

    try {
      final response = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.mobileRefresh,
        data: {'refresh_token': refreshToken, 'device_id': deviceId},
        options: Options(extra: {'requiresAuth': false}),
      );

      final body = response.data;
      final token = body?['token'] as String?;
      final rotated = body?['refresh_token'] as String?;
      if (token == null || token.isEmpty) {
        _log.warning('Refresh returned no token');
        return RefreshOutcome.rejected;
      }

      await _storage.writeToken(token);
      // The old refresh token is already dead server-side; failing to store
      // the replacement would strand the session on the next expiry.
      if (rotated != null && rotated.isNotEmpty) {
        await _storage.writeRefreshToken(rotated);
      }
      _log.info('Access token refreshed');
      return RefreshOutcome.refreshed;
    } on DioException catch (e) {
      final status = e.response?.statusCode;
      if (status == 401 || status == 403) {
        _log.warning('Refresh token rejected ($status) — session over');
        await _storage.deleteRefreshToken();
        return RefreshOutcome.rejected;
      }
      // A timeout or a 5xx says nothing about token validity. Treating it as
      // rejected would sign users out every time the HO server hiccups.
      _log.warning('Refresh failed transiently: ${e.type}');
      return RefreshOutcome.transient;
    }
  }
}
