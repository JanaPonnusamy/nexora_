import 'package:dio/dio.dart';

/// Normalised error surfaced to the UI/repository layer.
///
/// The FastAPI backend returns errors as `{ "detail": "..." }` (and some
/// endpoints use `{ "message" }` or `{ "error" }`). [ApiException.fromDio]
/// unwraps whichever is present so screens can show a clean message.
class ApiException implements Exception {
  const ApiException({
    required this.message,
    this.statusCode,
    this.isUnauthorized = false,
    this.isNetwork = false,
  });

  final String message;
  final int? statusCode;
  final bool isUnauthorized;
  final bool isNetwork;

  factory ApiException.fromDio(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return const ApiException(
          message: 'The server took too long to respond. Please try again.',
          isNetwork: true,
        );
      case DioExceptionType.connectionError:
        return const ApiException(
          message:
              'Cannot reach the server. Check your connection and the server address.',
          isNetwork: true,
        );
      case DioExceptionType.badCertificate:
        return const ApiException(
          message: 'The server certificate could not be verified.',
          isNetwork: true,
        );
      case DioExceptionType.cancel:
        return const ApiException(message: 'Request cancelled.');
      case DioExceptionType.badResponse:
      case DioExceptionType.unknown:
        final status = error.response?.statusCode;
        return ApiException(
          message: _extractMessage(error.response?.data) ??
              'Request failed${status != null ? ' ($status)' : ''}.',
          statusCode: status,
          isUnauthorized: status == 401,
        );
    }
  }

  static String? _extractMessage(dynamic data) {
    if (data is Map) {
      final detail = data['detail'] ?? data['message'] ?? data['error'];
      if (detail is String && detail.trim().isNotEmpty) return detail;
      // FastAPI validation errors: detail is a list of {msg, loc}
      if (detail is List && detail.isNotEmpty) {
        final first = detail.first;
        if (first is Map && first['msg'] is String) {
          return first['msg'] as String;
        }
      }
    }
    if (data is String && data.trim().isNotEmpty) return data;
    return null;
  }

  @override
  String toString() => 'ApiException($statusCode): $message';
}
