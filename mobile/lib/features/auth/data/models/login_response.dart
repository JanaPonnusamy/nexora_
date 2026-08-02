import 'package:freezed_annotation/freezed_annotation.dart';

import 'package:nexora_mobile/features/auth/data/models/app_user.dart';

part 'login_response.freezed.dart';
part 'login_response.g.dart';

/// Response of `POST /api/auth/login`:
///   { "token": "...", "token_type": "bearer", "user": { ... } }
@freezed
class LoginResponse with _$LoginResponse {
  const factory LoginResponse({
    required String token,
    @JsonKey(name: 'token_type') @Default('bearer') String tokenType,
    required AppUser user,
  }) = _LoginResponse;

  factory LoginResponse.fromJson(Map<String, dynamic> json) =>
      _$LoginResponseFromJson(json);
}
