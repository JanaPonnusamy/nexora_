import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/auth/data/models/login_response.dart';

/// Data access for authentication. Talks only to the existing backend auth
/// endpoints — no contract is invented here.
class AuthRepository {
  AuthRepository(this._dio);

  final Dio _dio;

  /// `POST /api/auth/login` — public (no bearer required).
  Future<LoginResponse> login({
    required String username,
    required String password,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.login,
        data: {'username': username, 'password': password},
        options: Options(extra: {'requiresAuth': false}),
      );
      return LoginResponse.fromJson(res.data!);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  /// `GET /api/auth/me` — validates the stored token and returns the fresh user.
  Future<AppUser> me() async {
    try {
      final res = await _dio.get<Map<String, dynamic>>(ApiEndpoints.me);
      return AppUser.fromJson(res.data!);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}
