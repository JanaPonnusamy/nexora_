import 'package:freezed_annotation/freezed_annotation.dart';

import 'package:nexora_mobile/features/auth/data/models/module_permission.dart';
import 'package:nexora_mobile/features/auth/data/models/user_role.dart';

part 'app_user.freezed.dart';
part 'app_user.g.dart';

/// The authenticated user as returned by `/api/auth/login` and `/api/auth/me`.
/// Field names/shape mirror `AuthService._serialize` on the backend exactly.
@freezed
class AppUser with _$AppUser {
  const AppUser._();

  const factory AppUser({
    @JsonKey(name: 'user_id') required String userId,
    required String username,
    @JsonKey(name: 'first_name') String? firstName,
    @JsonKey(name: 'is_platform_user') @Default(false) bool isPlatformUser,
    @JsonKey(name: 'is_active') @Default(true) bool isActive,
    @JsonKey(name: 'tenant_id') String? tenantId,
    @Default(<ModulePermission>[]) List<ModulePermission> modules,
    @Default(<UserRole>[]) List<UserRole> roles,
  }) = _AppUser;

  factory AppUser.fromJson(Map<String, dynamic> json) =>
      _$AppUserFromJson(json);

  /// Distinct, resolvable stores this user can act on, derived from [roles].
  /// A platform user may have none here and must pick from `/api/stores`.
  List<UserRole> get storeRoles =>
      roles.where((r) => r.storeId != null && r.storeId!.isNotEmpty).toList();

  String get displayName => (firstName != null && firstName!.trim().isNotEmpty)
      ? firstName!.trim()
      : username;
}
