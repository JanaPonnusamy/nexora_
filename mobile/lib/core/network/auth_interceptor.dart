import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/network/token_refresher.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';

/// Attaches the stored JWT as a `Bearer` header on every outgoing request, and
/// on a 401 tries to refresh the session before giving up on it.
///
/// Access tokens live 720 minutes (`UNINEX_JWT_EXPIRE_MINUTES`). Before the
/// mobile BFF existed, a 401 tore the session down immediately, so a user was
/// bounced to the login screen exactly 12 hours in — mid-task. Now a 401 on an
/// authenticated request triggers one refresh attempt and one retry, and only a
/// genuine rejection ends the session.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({
    required SecureStorageService storage,
    required Future<void> Function() onUnauthorized,
    TokenRefresher? refresher,
    Dio? retryClient,
  })  : _storage = storage,
        _onUnauthorized = onUnauthorized,
        _refresher = refresher,
        _retryClient = retryClient;

  final SecureStorageService _storage;
  final Future<void> Function() _onUnauthorized;
  final TokenRefresher? _refresher;

  /// Used to replay the original request after a successful refresh. Injected
  /// rather than constructed so it can be the app's own Dio (retries then keep
  /// base URL, timeouts and logging) without this class owning that wiring.
  final Dio? _retryClient;

  /// Marks a request as already retried, so a second 401 ends the session
  /// instead of looping.
  static const _retriedFlag = 'authRetried';

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
    final options = err.requestOptions;
    final requiresAuth = options.extra['requiresAuth'] != false;

    if (status != 401 || !requiresAuth) {
      handler.next(err);
      return;
    }

    final refresher = _refresher;
    final alreadyRetried = options.extra[_retriedFlag] == true;

    if (refresher == null || alreadyRetried) {
      await _onUnauthorized();
      handler.next(err);
      return;
    }

    final outcome = await refresher.refresh();

    switch (outcome) {
      case RefreshOutcome.refreshed:
        final retryClient = _retryClient;
        if (retryClient == null) {
          handler.next(err);
          return;
        }
        try {
          final token = await _storage.readToken();
          final retried = await retryClient.fetch<dynamic>(
            options
              ..extra[_retriedFlag] = true
              ..headers['Authorization'] = 'Bearer $token',
          );
          handler.resolve(retried);
        } on DioException catch (retryError) {
          handler.next(retryError);
        }

      case RefreshOutcome.rejected:
      case RefreshOutcome.unavailable:
        await _onUnauthorized();
        handler.next(err);

      case RefreshOutcome.transient:
        // The server could not be reached to confirm anything. Surface the
        // error and keep the session — the next call retries naturally.
        handler.next(err);
    }
  }
}
