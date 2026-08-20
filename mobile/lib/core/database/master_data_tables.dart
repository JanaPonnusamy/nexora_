import 'package:drift/drift.dart';

/// Phase 4 — offline business **master data** tables. These are non-transactional
/// reference tables only (no stock, purchase, sales, invoices). Every table is
/// tenant/store scoped and carries the delta-sync bookkeeping columns so the
/// generic sync engine can track versions, soft-deletes and last-sync per row.

/// Columns shared by every simple master table (department, category,
/// manufacturer, unit, tax). Kept in a mixin so the schema stays DRY.
mixin MasterColumns on Table {
  /// Owning tenant. Part of the primary key so the same server id can coexist
  /// across tenants on one device.
  TextColumn get tenantId => text().withDefault(const Constant(''))();

  /// Business code (e.g. department code). May differ from [Table]-specific id.
  TextColumn get code => text().withDefault(const Constant(''))();
  TextColumn get name => text().withDefault(const Constant(''))();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();

  /// Server-supplied row version, when the backend exposes one (see
  /// docs/API_CONTRACT.md — most master endpoints do not yet).
  IntColumn get version => integer().nullable()();

  /// Server-supplied last-modified timestamp used as the delta watermark source.
  DateTimeColumn get serverUpdatedAt => dateTime().nullable()();

  /// Soft-delete tombstone. Rows are never hard-deleted by sync so the UI can
  /// distinguish "removed upstream" from "never synced".
  BoolColumn get isDeleted => boolean().withDefault(const Constant(false))();

  /// When this row was last written by a sync.
  DateTimeColumn get syncedAt => dateTime().withDefault(currentDateAndTime)();
}

@DataClassName('DepartmentRow')
class Departments extends Table with MasterColumns {
  TextColumn get id => text()();

  @override
  Set<Column> get primaryKey => {tenantId, id};
}

@DataClassName('CategoryRow')
class Categories extends Table with MasterColumns {
  TextColumn get id => text()();

  /// Optional parent category for hierarchical catalogues.
  TextColumn get parentId => text().nullable()();

  @override
  Set<Column> get primaryKey => {tenantId, id};
}

@DataClassName('ManufacturerRow')
class Manufacturers extends Table with MasterColumns {
  TextColumn get id => text()();

  @override
  Set<Column> get primaryKey => {tenantId, id};
}

@DataClassName('UnitRow')
class Units extends Table with MasterColumns {
  TextColumn get id => text()();

  @override
  Set<Column> get primaryKey => {tenantId, id};
}

@DataClassName('TaxRow')
class TaxMaster extends Table with MasterColumns {
  TextColumn get id => text()();

  /// Tax rate as a percentage (e.g. 5.0 for 5%).
  RealColumn get ratePercent => real().nullable()();

  @override
  Set<Column> get primaryKey => {tenantId, id};
}

/// Suppliers are store-scoped and sourced from the supplier-stock-analysis
/// endpoint (see docs/API_CONTRACT.md — it reflects suppliers with imported
/// stock, not the full supplier master).
@DataClassName('SupplierRow')
class Suppliers extends Table {
  TextColumn get tenantId => text().withDefault(const Constant(''))();
  TextColumn get storeId => text().withDefault(const Constant(''))();
  TextColumn get supplierCode => text()();
  TextColumn get supplierName => text().withDefault(const Constant(''))();
  IntColumn get productCount => integer().withDefault(const Constant(0))();
  IntColumn get availableCount => integer().withDefault(const Constant(0))();
  RealColumn get totalAvailableStock => real().withDefault(const Constant(0))();
  DateTimeColumn get lastImportedAt => dateTime().nullable()();
  BoolColumn get isActive => boolean().withDefault(const Constant(true))();
  IntColumn get version => integer().nullable()();
  BoolColumn get isDeleted => boolean().withDefault(const Constant(false))();
  DateTimeColumn get syncedAt => dateTime().withDefault(currentDateAndTime)();

  @override
  Set<Column> get primaryKey => {tenantId, storeId, supplierCode};
}
