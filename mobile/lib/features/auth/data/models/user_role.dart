import 'package:freezed_annotation/freezed_annotation.dart';

part 'user_role.freezed.dart';
part 'user_role.g.dart';

/// A role the user holds, scoped to a store. This is the authoritative list of
/// stores a (non-platform) user may operate on — the store selection screen is
/// driven from these entries. Mirrors the backend `roles[]` shape.
@freezed
class UserRole with _$UserRole {
  const factory UserRole({
    @JsonKey(name: 'role_id') required String roleId,
    @JsonKey(name: 'role_name') required String roleName,
    @JsonKey(name: 'store_id') String? storeId,
    @JsonKey(name: 'store_code') String? storeCode,
    @JsonKey(name: 'store_name') String? storeName,
  }) = _UserRole;

  factory UserRole.fromJson(Map<String, dynamic> json) =>
      _$UserRoleFromJson(json);
}
