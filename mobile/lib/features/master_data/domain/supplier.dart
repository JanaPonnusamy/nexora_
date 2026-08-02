import 'package:drift/drift.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/features/master_data/data/master_json.dart';

/// Domain model for a supplier (store-scoped offline master data).
///
/// Sourced from `GET /api/supplier-stock-analysis/suppliers`, which returns
/// suppliers that have imported stock for the store (with stock counts) — see
/// docs/API_CONTRACT.md for the caveat that this is not the full supplier
/// master.
class Supplier {
  const Supplier({
    required this.tenantId,
    required this.storeId,
    required this.supplierCode,
    required this.supplierName,
    this.productCount = 0,
    this.availableCount = 0,
    this.totalAvailableStock = 0,
    this.lastImportedAt,
    this.isActive = true,
    this.version,
    this.isDeleted = false,
    this.syncedAt,
  });

  final String tenantId;
  final String storeId;
  final String supplierCode;
  final String supplierName;
  final int productCount;
  final int availableCount;
  final double totalAvailableStock;
  final DateTime? lastImportedAt;
  final bool isActive;
  final int? version;
  final bool isDeleted;
  final DateTime? syncedAt;
}

class SupplierDto {
  const SupplierDto({
    required this.supplierCode,
    required this.supplierName,
    this.productCount = 0,
    this.availableCount = 0,
    this.totalAvailableStock = 0,
    this.lastImportedAt,
  });

  final String supplierCode;
  final String supplierName;
  final int productCount;
  final int availableCount;
  final double totalAvailableStock;
  final DateTime? lastImportedAt;

  factory SupplierDto.fromJson(Map<String, dynamic> json) {
    return SupplierDto(
      supplierCode: stringField(json, ['supplier_code', 'supplierCode', 'code']),
      supplierName:
          stringField(json, ['supplier_name', 'supplierName', 'name']),
      productCount: asInt(firstOf(json, ['product_count', 'productCount'])),
      availableCount:
          asInt(firstOf(json, ['available_count', 'availableCount'])),
      totalAvailableStock: asDouble(
          firstOf(json, ['total_available_stock', 'totalAvailableStock']),),
      lastImportedAt: asDateOrNull(
          firstOf(json, ['last_imported_at', 'lastImportedAt', 'imported_at']),),
    );
  }
}

class SupplierMapper {
  const SupplierMapper._();

  static SuppliersCompanion toCompanion(
    SupplierDto dto, {
    required String tenantId,
    required String storeId,
    required DateTime syncedAt,
  }) {
    return SuppliersCompanion(
      tenantId: Value(tenantId),
      storeId: Value(storeId),
      supplierCode: Value(dto.supplierCode),
      supplierName: Value(dto.supplierName),
      productCount: Value(dto.productCount),
      availableCount: Value(dto.availableCount),
      totalAvailableStock: Value(dto.totalAvailableStock),
      lastImportedAt: Value(dto.lastImportedAt),
      isActive: const Value(true),
      isDeleted: const Value(false),
      syncedAt: Value(syncedAt),
    );
  }

  static Supplier fromRow(SupplierRow row) => Supplier(
        tenantId: row.tenantId,
        storeId: row.storeId,
        supplierCode: row.supplierCode,
        supplierName: row.supplierName,
        productCount: row.productCount,
        availableCount: row.availableCount,
        totalAvailableStock: row.totalAvailableStock,
        lastImportedAt: row.lastImportedAt,
        isActive: row.isActive,
        version: row.version,
        isDeleted: row.isDeleted,
        syncedAt: row.syncedAt,
      );
}
