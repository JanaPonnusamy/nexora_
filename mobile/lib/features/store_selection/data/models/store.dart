import 'package:freezed_annotation/freezed_annotation.dart';

part 'store.freezed.dart';
part 'store.g.dart';

/// A store as returned by `GET /api/stores` (and `GET /api/stores/{id}`).
///
/// The tenant-scoped endpoint `GET /api/stores/tenant/{tenant_id}` returns a
/// slimmer projection (only `store_id`, `store_code`, `store_name`); the extra
/// fields here are nullable so a single model covers both.
@freezed
class Store with _$Store {
  const factory Store({
    @JsonKey(name: 'store_id') required String storeId,
    @JsonKey(name: 'tenant_id') String? tenantId,
    @JsonKey(name: 'store_code') required String storeCode,
    @JsonKey(name: 'store_name') required String storeName,
    @JsonKey(name: 'server_name') String? serverName,
    @JsonKey(name: 'database_name') String? databaseName,
    @JsonKey(name: 'is_active') @Default(true) bool isActive,
  }) = _Store;

  factory Store.fromJson(Map<String, dynamic> json) => _$StoreFromJson(json);
}
