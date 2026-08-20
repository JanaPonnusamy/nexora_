import 'package:freezed_annotation/freezed_annotation.dart';

import 'package:nexora_mobile/features/auth/data/models/app_user.dart';

part 'login_response.freezed.dart';
part 'login_response.g.dart';

/// Response of `POST /api/mobile/v1/auth/login`:
///   { "token": "...", "token_type": "bearer", "expires_in": 43200,
///     "refresh_token": "...", "refresh_expires_in": 2592000, "user": {...} }
///
/// The refresh fields are nullable so the same model still parses
/// `POST /api/auth/login`, which returns only `token`/`token_type`/`user` and
/// remains the fallback when a server predates the mobile BFF.
@freezed
class LoginResponse with _$LoginResponse {
  const factory LoginResponse({
    required String token,
    @JsonKey(name: 'token_type') @Default('bearer') String tokenType,
    @JsonKey(name: 'refresh_token') String? refreshToken,
    @JsonKey(name: 'expires_in') int? expiresIn,
    @JsonKey(name: 'refresh_expires_in') int? refreshExpiresIn,
    required AppUser user,
  }) = _LoginResponse;

  factory LoginResponse.fromJson(Map<String, dynamic> json) =>
      _$LoginResponseFromJson(json);
}
