import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/services/app_logger.dart';

/// Lightweight request/response logger. Never logs the Authorization header or
/// request bodies (which contain credentials) to avoid leaking secrets.
class LoggingInterceptor extends Interceptor {
  LoggingInterceptor({required this.enabled});

  final bool enabled;
  final _log = AppLogger.of('Http');

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    if (enabled) {
      _log.fine('→ ${options.method} ${options.uri}');
    }
    handler.next(options);
  }

  @override
  void onResponse(Response response, ResponseInterceptorHandler handler) {
    if (enabled) {
      _log.fine(
        '← ${response.statusCode} ${response.requestOptions.method} '
        '${response.requestOptions.uri}',
      );
    }
    handler.next(response);
  }

  @override
  void onError(DioException err, ErrorInterceptorHandler handler) {
    if (enabled) {
      _log.warning(
        '✗ ${err.response?.statusCode ?? '-'} '
        '${err.requestOptions.method} ${err.requestOptions.uri} '
        '(${err.type.name})',
      );
    }
    handler.next(err);
  }
}
