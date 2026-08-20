import 'package:freezed_annotation/freezed_annotation.dart';

part 'module_permission.freezed.dart';
part 'module_permission.g.dart';

/// A single module access row from the login/`/api/auth/me` payload.
/// Mirrors the backend `modules[]` shape (see `AuthService._serialize`).
@freezed
class ModulePermission with _$ModulePermission {
  const factory ModulePermission({
    required String module,
    required String name,
    @JsonKey(name: 'can_view') @Default(false) bool canView,
    @JsonKey(name: 'can_create') @Default(false) bool canCreate,
    @JsonKey(name: 'can_edit') @Default(false) bool canEdit,
    @JsonKey(name: 'can_delete') @Default(false) bool canDelete,
    @JsonKey(name: 'can_export') @Default(false) bool canExport,
  }) = _ModulePermission;

  factory ModulePermission.fromJson(Map<String, dynamic> json) =>
      _$ModulePermissionFromJson(json);
}
