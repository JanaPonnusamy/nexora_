import 'package:nexora_mobile/features/master_data/data/category_repository.dart';
import 'package:nexora_mobile/features/master_data/data/department_repository.dart';
import 'package:nexora_mobile/features/master_data/data/manufacturer_repository.dart';
import 'package:nexora_mobile/features/master_data/data/master_data_api_service.dart';
import 'package:nexora_mobile/features/master_data/data/supplier_repository.dart';
import 'package:nexora_mobile/features/master_data/data/tax_rate_repository.dart';
import 'package:nexora_mobile/features/master_data/data/unit_repository.dart';
import 'package:nexora_mobile/features/master_data/sync/master_delta_processor.dart';

/// Canonical entity names used as sync-queue/metadata keys. Kept distinct from
/// the Phase-2/3 entities (`store_config`, `user_profile`).
class MasterEntities {
  const MasterEntities._();
  static const departments = 'departments';
  static const categories = 'categories';
  static const manufacturers = 'manufacturers';
  static const units = 'units';
  static const taxMaster = 'tax_master';
  static const suppliers = 'suppliers';

  static const all = <String>[
    departments,
    categories,
    manufacturers,
    units,
    taxMaster,
    suppliers,
  ];
}

/// Suppliers — the one entity with a real backend endpoint (a full snapshot from
/// supplier-stock-analysis). Store-scoped.
class SupplierDeltaProcessor extends MasterDeltaProcessor {
  SupplierDeltaProcessor({
    required SupplierRepository repository,
    required MasterDataApiService api,
    required super.scope,
    super.logger,
  }) : super(
          entity: MasterEntities.suppliers,
          writer: repository,
          storeScoped: true,
          fetch: (s, {watermark}) =>
              api.fetchSuppliers(s, watermark: watermark),
        );
}

/// Departments — no backend read endpoint yet (documented gap); no-ops safely.
class DepartmentDeltaProcessor extends MasterDeltaProcessor {
  DepartmentDeltaProcessor({
    required DepartmentRepository repository,
    required super.scope,
    super.logger,
  }) : super(
          entity: MasterEntities.departments,
          writer: repository,
        );
}

/// Categories — no backend read endpoint yet (documented gap); no-ops safely.
class CategoryDeltaProcessor extends MasterDeltaProcessor {
  CategoryDeltaProcessor({
    required CategoryRepository repository,
    required super.scope,
    super.logger,
  }) : super(
          entity: MasterEntities.categories,
          writer: repository,
        );
}

/// Manufacturers — no backend read endpoint yet (documented gap); no-ops safely.
class ManufacturerDeltaProcessor extends MasterDeltaProcessor {
  ManufacturerDeltaProcessor({
    required ManufacturerRepository repository,
    required super.scope,
    super.logger,
  }) : super(
          entity: MasterEntities.manufacturers,
          writer: repository,
        );
}

/// Units — no backend read endpoint yet (documented gap); no-ops safely.
class UnitDeltaProcessor extends MasterDeltaProcessor {
  UnitDeltaProcessor({
    required UnitRepository repository,
    required super.scope,
    super.logger,
  }) : super(
          entity: MasterEntities.units,
          writer: repository,
        );
}

/// Tax master — no backend read endpoint yet (documented gap); no-ops safely.
class TaxRateDeltaProcessor extends MasterDeltaProcessor {
  TaxRateDeltaProcessor({
    required TaxRateRepository repository,
    required super.scope,
    super.logger,
  }) : super(
          entity: MasterEntities.taxMaster,
          writer: repository,
        );
}
