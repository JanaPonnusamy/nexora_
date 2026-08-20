import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/master_data/data/master_json.dart';

/// Domain model for a unit of measure (offline master data).
class Unit {
  const Unit({
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

class UnitDto {
  const UnitDto({
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

  factory UnitDto.fromJson(Map<String, dynamic> json) {
    final code = stringField(json, ['code', 'unit_code', 'uom_code', 'uom']);
    return UnitDto(
      id: stringField(
        json,
        ['id', 'unit_id', 'code', 'unit_code'],
        fallback: code,
      ),
      code: code,
      name: stringField(json, ['name', 'unit_name', 'uom_name', 'description']),
      isActive: asBool(firstOf(json, ['is_active', 'isActive', 'active'])),
      version: asIntOrNull(firstOf(json, ['version', 'row_version'])),
      updatedAt: asDateOrNull(
        firstOf(json, ['updated_at', 'updatedAt', 'modified_at']),
      ),
    );
  }
}

class UnitMapper {
  const UnitMapper._();

  static UnitsCompanion toCompanion(
    UnitDto dto, {
    required String tenantId,
    required DateTime syncedAt,
  }) {
    return UnitsCompanion(
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

  static Unit fromRow(UnitRow row) => Unit(
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
