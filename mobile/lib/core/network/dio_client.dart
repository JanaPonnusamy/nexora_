import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/config/app_config.dart';
import 'package:nexora_mobile/core/network/auth_interceptor.dart';
import 'package:nexora_mobile/core/network/logging_interceptor.dart';
import 'package:nexora_mobile/core/services/secure_storage_service.dart';

/// Factory for the single, shared [Dio] instance used by every repository.
///
/// Wiring lives here; construction is driven by Riverpod providers
/// (`core/di/providers.dart`) so it stays testable and there is exactly one
/// client per app session.
class DioClient {
  static Dio create({
    required AppConfig config,
    required SecureStorageService storage,
    required Future<void> Function() onUnauthorized,
  }) {
    final dio = Dio(
      BaseOptions(
        baseUrl: config.apiBaseUrl,
        connectTimeout: config.connectTimeout,
        receiveTimeout: config.receiveTimeout,
        // Do not throw on non-2xx here; ApiException handling is centralised in
        // the repositories via DioException, and 401 is handled by the
        // interceptor. We keep Dio's default validateStatus (throws on >=400)
        // so errors surface as DioException.
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      ),
    );

    dio.interceptors.addAll([
      AuthInterceptor(storage: storage, onUnauthorized: onUnauthorized),
      LoggingInterceptor(enabled: config.enableVerboseLogging),
    ]);

    return dio;
  }
}
