import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/master_data/data/master_json.dart';

/// Domain model for a product category (offline master data).
class Category {
  const Category({
    required this.id,
    required this.tenantId,
    required this.code,
    required this.name,
    this.parentId,
    this.isActive = true,
    this.version,
    this.serverUpdatedAt,
    this.isDeleted = false,
    this.syncedAt,
  });

  final String id;
  final String tenantId;
  final String code;
  final String name;
  final String? parentId;
  final bool isActive;
  final int? version;
  final DateTime? serverUpdatedAt;
  final bool isDeleted;
  final DateTime? syncedAt;
}

class CategoryDto {
  const CategoryDto({
    required this.id,
    required this.code,
    required this.name,
    this.parentId,
    this.isActive = true,
    this.version,
    this.updatedAt,
  });

  final String id;
  final String code;
  final String name;
  final String? parentId;
  final bool isActive;
  final int? version;
  final DateTime? updatedAt;

  factory CategoryDto.fromJson(Map<String, dynamic> json) {
    final code = stringField(json, ['code', 'category_code', 'cat_code']);
    final parent =
        firstOf(json, ['parent_id', 'parentId', 'parent_code', 'parent']);
    return CategoryDto(
      id: stringField(json, ['id', 'category_id', 'code', 'category_code'],
          fallback: code,),
      code: code,
      name: stringField(json, ['name', 'category_name', 'cat_name']),
      parentId: parent == null ? null : asString(parent),
      isActive: asBool(firstOf(json, ['is_active', 'isActive', 'active'])),
      version: asIntOrNull(firstOf(json, ['version', 'row_version'])),
      updatedAt: asDateOrNull(
          firstOf(json, ['updated_at', 'updatedAt', 'modified_at']),),
    );
  }
}

class CategoryMapper {
  const CategoryMapper._();

  static CategoriesCompanion toCompanion(
    CategoryDto dto, {
    required String tenantId,
    required DateTime syncedAt,
  }) {
    return CategoriesCompanion(
      tenantId: Value(tenantId),
      id: Value(dto.id),
      code: Value(dto.code),
      name: Value(dto.name),
      parentId: Value(dto.parentId),
      isActive: Value(dto.isActive),
      version: Value(dto.version),
      serverUpdatedAt: Value(dto.updatedAt),
      isDeleted: const Value(false),
      syncedAt: Value(syncedAt),
    );
  }

  static Category fromRow(CategoryRow row) => Category(
        id: row.id,
        tenantId: row.tenantId,
        code: row.code,
        name: row.name,
        parentId: row.parentId,
        isActive: row.isActive,
        version: row.version,
        serverUpdatedAt: row.serverUpdatedAt,
        isDeleted: row.isDeleted,
        syncedAt: row.syncedAt,
      );
}
