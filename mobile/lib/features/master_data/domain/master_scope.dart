/// The tenant / store / user context a master-data sync runs within.
///
/// Nothing global is assumed: every pull and every repository read is scoped to
/// the signed-in user's tenant (and store, where the entity is store-scoped).
class MasterScope {
  const MasterScope({
    required this.tenantId,
    this.storeId,
    this.userId,
  });

  const MasterScope.empty()
      : tenantId = '',
        storeId = null,
        userId = null;

  final String tenantId;
  final String? storeId;
  final String? userId;

  /// A tenant is the minimum required to scope tenant-level master data.
  bool get hasTenant => tenantId.isNotEmpty;

  /// Store-scoped entities additionally need a selected store.
  bool get hasStore => (storeId ?? '').isNotEmpty;

  @override
  String toString() =>
      'MasterScope(tenant=$tenantId, store=$storeId, user=$userId)';
}
