import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/master_data/data/master_json.dart';

/// Domain model for a department (offline master data).
class Department {
  const Department({
    required this.id,
    required this.tenantId,
    required this.code,
    required this.name,
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
  final bool isActive;
  final int? version;
  final DateTime? serverUpdatedAt;
  final bool isDeleted;
  final DateTime? syncedAt;
}

/// Wire shape parsed from a backend record (field names coerced loosely).
class DepartmentDto {
  const DepartmentDto({
    required this.id,
    required this.code,
    required this.name,
    this.isActive = true,
    this.version,
    this.updatedAt,
  });

  final String id;
  final String code;
  final String name;
  final bool isActive;
  final int? version;
  final DateTime? updatedAt;

  factory DepartmentDto.fromJson(Map<String, dynamic> json) {
    final code = stringField(json, ['code', 'department_code', 'dept_code']);
    return DepartmentDto(
      id: stringField(
        json,
        ['id', 'department_id', 'code', 'department_code'],
        fallback: code,
      ),
      code: code,
      name: stringField(json, ['name', 'department_name', 'dept_name']),
      isActive: asBool(firstOf(json, ['is_active', 'isActive', 'active'])),
      version:
          asIntOrNull(firstOf(json, ['version', 'row_version', 'rowversion'])),
      updatedAt: asDateOrNull(
        firstOf(
            json, ['updated_at', 'updatedAt', 'modified_at', 'last_modified']),
      ),
    );
  }
}

/// Converts between the DTO, the Drift companion and the domain model.
class DepartmentMapper {
  const DepartmentMapper._();

  static DepartmentsCompanion toCompanion(
    DepartmentDto dto, {
    required String tenantId,
    required DateTime syncedAt,
  }) {
    return DepartmentsCompanion(
      tenantId: Value(tenantId),
      id: Value(dto.id),
      code: Value(dto.code),
      name: Value(dto.name),
      isActive: Value(dto.isActive),
      version: Value(dto.version),
      serverUpdatedAt: Value(dto.updatedAt),
      isDeleted: const Value(false),
      syncedAt: Value(syncedAt),
    );
  }

  static Department fromRow(DepartmentRow row) => Department(
        id: row.id,
        tenantId: row.tenantId,
        code: row.code,
        name: row.name,
        isActive: row.isActive,
        version: row.version,
        serverUpdatedAt: row.serverUpdatedAt,
        isDeleted: row.isDeleted,
        syncedAt: row.syncedAt,
      );
}
