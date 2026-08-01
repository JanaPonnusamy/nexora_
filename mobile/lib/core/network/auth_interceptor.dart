import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/services/secure_storage_service.dart';

/// Attaches the stored JWT as a `Bearer` header on every outgoing request and
/// signals the app when the server rejects the token (401) so the session can
/// be torn down and the user returned to the login screen.
///
/// Mirrors the desktop client's behaviour (`src/api/client.js`), where a 401
/// on an authenticated request dispatches a `nexora:unauthorized` event.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required SecureStorageService storage,
    required Future<void> Function() onUnauthorized,
  })  : _storage = storage,
        _onUnauthorized = onUnauthorized;

  final SecureStorageService _storage;
  final Future<void> Function() _onUnauthorized;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    // Opt out per-request for public endpoints (login, health) via extra flag.
    final requiresAuth = options.extra['requiresAuth'] != false;
    if (requiresAuth) {
      final token = await _storage.readToken();
      if (token != null && token.isNotEmpty) {
        options.headers['Authorization'] = 'Bearer $token';
      }
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final status = err.response?.statusCode;
    final requiresAuth = err.requestOptions.extra['requiresAuth'] != false;
    if (status == 401 && requiresAuth) {
      await _onUnauthorized();
    }
    handler.next(err);
  }
}
