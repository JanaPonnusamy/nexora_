import 'package:dio/dio.dart';

import 'package:nexora_mobile/core/api/api_endpoints.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/auth/data/models/login_response.dart';

/// Device identity sent with a mobile login. The refresh-token chain the
/// server issues is bound to [deviceId], so it must be the stable per-install
/// id from secure storage.
class DeviceDescriptor {
  const DeviceDescriptor({
    required this.deviceId,
    this.deviceName,
    this.platform,
    this.appVersion,
  });

  final String deviceId;
  final String? deviceName;
  final String? platform;
  final String? appVersion;

  Map<String, dynamic> toJson() => {
        'device_id': deviceId,
        if (deviceName != null) 'device_name': deviceName,
        if (platform != null) 'platform': platform,
        if (appVersion != null) 'app_version': appVersion,
      };
}

/// Data access for authentication. Talks only to the existing backend auth
/// endpoints — no contract is invented here.
class AuthRepository {
  AuthRepository(this._dio);

  final Dio _dio;

  /// Signs in via `POST /api/mobile/v1/auth/login` — public (no bearer).
  ///
  /// Prefers the mobile BFF because it also returns a refresh token; without
  /// one the session dies at the 12-hour access-token expiry. Falls back to
  /// `POST /api/auth/login` when the BFF is absent (404), so the app still
  /// works against an HO server that has not been upgraded yet — the session
  /// is simply not refreshable there.
  Future<LoginResponse> login({
    required String username,
    required String password,
    required DeviceDescriptor device,
  }) async {
    try {
      final res = await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.mobileLogin,
        data: {
          'username': username,
          'password': password,
          'device': device.toJson(),
        },
        options: Options(extra: {'requiresAuth': false}),
      );
      return LoginResponse.fromJson(res.data!);
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) {
        return _legacyLogin(username: username, password: password);
      }
      throw ApiException.fromDio(e);
    }
  }

  Future<LoginResponse> _legacyLogin({
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

  /// `POST /api/mobile/v1/auth/logout` — revokes the refresh chain server-side.
  /// Best-effort: local sign-out must succeed even when the server is
  /// unreachable, so failures are swallowed.
  Future<void> logout({String? refreshToken, String? deviceId}) async {
    try {
      await _dio.post<Map<String, dynamic>>(
        ApiEndpoints.mobileLogout,
        data: {'refresh_token': refreshToken, 'device_id': deviceId},
      );
    } on DioException {
      return;
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
