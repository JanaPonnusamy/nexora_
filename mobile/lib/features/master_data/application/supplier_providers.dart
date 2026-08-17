import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/features/master_data/domain/supplier.dart';

/// Suppliers are read **entirely from the local Drift cache** — never straight
/// off the network.
///
/// That is what makes the module usable in a stockroom: the master is synced
/// by the existing engine and the screen just watches the table, so search
/// works with no signal at all. A network read here would make the one place
/// the field team needs offline the one place that requires a connection.
final supplierListProvider = StreamProvider.autoDispose<List<Supplier>>((ref) {
  final scope = ref.watch(masterScopeProvider)();
  if (!scope.hasTenant || !scope.hasStore) return Stream.value(const []);
  return ref.watch(supplierRepositoryProvider).watchAll(scope);
});

/// Free-text filter applied on-device across code and name.
final supplierQueryProvider = StateProvider.autoDispose<String>((_) => '');

/// How the list is ordered. Suppliers arrive alphabetically from the
/// repository; the other orders answer "who am I carrying the most stock for?"
enum SupplierSort {
  name('Name'),
  stock('Stock'),
  products('Products');

  const SupplierSort(this.label);

  final String label;
}

final supplierSortProvider =
    StateProvider.autoDispose<SupplierSort>((_) => SupplierSort.name);

/// The list as the screen renders it: filtered, then sorted.
final filteredSuppliersProvider =
    Provider.autoDispose<AsyncValue<List<Supplier>>>((ref) {
  final suppliers = ref.watch(supplierListProvider);
  final query = ref.watch(supplierQueryProvider).trim().toLowerCase();
  final sort = ref.watch(supplierSortProvider);

  return suppliers.whenData((list) {
    final filtered = query.isEmpty
        ? [...list]
        : list
            .where(
              (s) =>
                  s.supplierName.toLowerCase().contains(query) ||
                  s.supplierCode.toLowerCase().contains(query),
            )
            .toList();

    filtered.sort(switch (sort) {
      SupplierSort.name => (a, b) =>
          a.supplierName.toLowerCase().compareTo(b.supplierName.toLowerCase()),
      // Descending for the quantitative sorts: "most stock" is the question
      // being asked, and an ascending list of zeroes answers nothing.
      SupplierSort.stock => (a, b) =>
          b.totalAvailableStock.compareTo(a.totalAvailableStock),
      SupplierSort.products => (a, b) =>
          b.productCount.compareTo(a.productCount),
    });
    return filtered;
  });
});

/// One supplier by code, for the detail sheet.
final supplierByCodeProvider =
    FutureProvider.autoDispose.family<Supplier?, String>((ref, code) {
  final scope = ref.watch(masterScopeProvider)();
  if (!scope.hasTenant || !scope.hasStore) return Future.value(null);
  return ref.watch(supplierRepositoryProvider).getByCode(scope, code);
});
