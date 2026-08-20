import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/master_data/data/master_json.dart';

/// Domain model for a tax-master entry (offline master data).
class TaxRate {
  const TaxRate({
    required this.id,
    required this.tenantId,
    required this.code,
    required this.name,
    this.ratePercent,
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
  final double? ratePercent;
  final bool isActive;
  final int? version;
  final DateTime? serverUpdatedAt;
  final bool isDeleted;
  final DateTime? syncedAt;
}

class TaxRateDto {
  const TaxRateDto({
    required this.id,
    required this.code,
    required this.name,
    this.ratePercent,
    this.isActive = true,
    this.version,
    this.updatedAt,
  });

  final String id;
  final String code;
  final String name;
  final double? ratePercent;
  final bool isActive;
  final int? version;
  final DateTime? updatedAt;

  factory TaxRateDto.fromJson(Map<String, dynamic> json) {
    final code = stringField(json, ['code', 'tax_code', 'taxcode']);
    final rate = firstOf(json,
        ['rate_percent', 'ratePercent', 'rate', 'tax_percent', 'percentage']);
    return TaxRateDto(
      id: stringField(json, ['id', 'tax_id', 'code', 'tax_code'],
          fallback: code),
      code: code,
      name: stringField(json, ['name', 'tax_name', 'description']),
      ratePercent: rate == null ? null : asDouble(rate),
      isActive: asBool(firstOf(json, ['is_active', 'isActive', 'active'])),
      version: asIntOrNull(firstOf(json, ['version', 'row_version'])),
      updatedAt: asDateOrNull(
        firstOf(json, ['updated_at', 'updatedAt', 'modified_at']),
      ),
    );
  }
}

class TaxRateMapper {
  const TaxRateMapper._();

  static TaxMasterCompanion toCompanion(
    TaxRateDto dto, {
    required String tenantId,
    required DateTime syncedAt,
  }) {
    return TaxMasterCompanion(
      tenantId: Value(tenantId),
      id: Value(dto.id),
      code: Value(dto.code),
      name: Value(dto.name),
      ratePercent: Value(dto.ratePercent),
      isActive: Value(dto.isActive),
      version: Value(dto.version),
      serverUpdatedAt: Value(dto.updatedAt),
      isDeleted: const Value(false),
      syncedAt: Value(syncedAt),
    );
  }

  static TaxRate fromRow(TaxRow row) => TaxRate(
        id: row.id,
        tenantId: row.tenantId,
        code: row.code,
        name: row.name,
        ratePercent: row.ratePercent,
        isActive: row.isActive,
        version: row.version,
        serverUpdatedAt: row.serverUpdatedAt,
        isDeleted: row.isDeleted,
        syncedAt: row.syncedAt,
      );
}
