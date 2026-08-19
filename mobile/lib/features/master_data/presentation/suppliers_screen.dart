import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/agent/presentation/widgets/status_widgets.dart';
import 'package:nexora_mobile/features/master_data/application/supplier_providers.dart';
import 'package:nexora_mobile/features/master_data/domain/supplier.dart';

/// The supplier master — net-new for mobile; the web console has no equivalent
/// screen.
///
/// Reads only the local cache, so it works with no signal. The sync engine
/// keeps that cache fresh; pull-to-refresh asks it to run now rather than
/// fetching here, which keeps one code path responsible for the data.
class SuppliersScreen extends ConsumerStatefulWidget {
  const SuppliersScreen({super.key});

  @override
  ConsumerState<SuppliersScreen> createState() => _SuppliersScreenState();
}

class _SuppliersScreenState extends ConsumerState<SuppliersScreen> {
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _openDetail(Supplier supplier) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.surfaceRaised,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _SupplierDetailSheet(supplier: supplier),
    );
  }

  @override
  Widget build(BuildContext context) {
    final suppliers = ref.watch(filteredSuppliersProvider);
    final sort = ref.watch(supplierSortProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Suppliers')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: TextField(
              controller: _search,
              decoration: InputDecoration(
                hintText: 'Search by name or code',
                prefixIcon: const Icon(Icons.search_rounded),
                suffixIcon: _search.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close_rounded, size: 18),
                        onPressed: () {
                          _search.clear();
                          ref.read(supplierQueryProvider.notifier).state = '';
                        },
                      ),
              ),
              onChanged: (v) =>
                  ref.read(supplierQueryProvider.notifier).state = v,
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: Row(
              children: [
                const Text(
                  'Sort',
                  style: TextStyle(fontSize: 12, color: AppColors.textMuted),
                ),
                const SizedBox(width: 10),
                for (final option in SupplierSort.values)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(option.label),
                      selected: sort == option,
                      onSelected: (_) => ref
                          .read(supplierSortProvider.notifier)
                          .state = option,
                    ),
                  ),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              // The sync engine owns fetching. Asking it to run keeps a single
              // path responsible for reconciling deletions and versions.
              onRefresh: () => ref.read(agentManagerProvider).triggerSync(),
              child: suppliers.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => _Scrollable(
                  child: EmptyState(
                    message: 'Could not read the supplier cache.\n$e',
                    icon: Icons.error_outline_rounded,
                  ),
                ),
                data: (list) => list.isEmpty
                    ? _Scrollable(child: _emptyState())
                    : ListView.builder(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
                        itemCount: list.length + 1,
                        itemBuilder: (context, index) {
                          if (index == 0) return _CountLine(suppliers: list);
                          final supplier = list[index - 1];
                          return _SupplierCard(
                            supplier: supplier,
                            onTap: () => _openDetail(supplier),
                          );
                        },
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _emptyState() {
    final searching = ref.read(supplierQueryProvider).trim().isNotEmpty;
    return EmptyState(
      message: searching
          ? 'No supplier matches that search.'
          : 'No suppliers cached yet.\nPull down to sync.',
      icon:
          searching ? Icons.search_off_rounded : Icons.local_shipping_outlined,
    );
  }
}

class _CountLine extends StatelessWidget {
  const _CountLine({required this.suppliers});

  final List<Supplier> suppliers;

  @override
  Widget build(BuildContext context) {
    final synced =
        suppliers.map((s) => s.syncedAt).whereType<DateTime>().fold<DateTime?>(
              null,
              (latest, d) => latest == null || d.isAfter(latest) ? d : latest,
            );

    return Padding(
      padding: const EdgeInsets.only(bottom: 10, left: 2, right: 2),
      child: Row(
        children: [
          Expanded(
            child: Text(
              '${suppliers.length} supplier'
              '${suppliers.length == 1 ? '' : 's'}',
              style: const TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w700,
                color: AppColors.textMuted,
              ),
            ),
          ),
          // A cached list is only trustworthy if it says how old it is.
          Text(
            'Synced ${formatRelative(synced)}',
            style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
          ),
        ],
      ),
    );
  }
}

class _SupplierCard extends StatelessWidget {
  const _SupplierCard({required this.supplier, required this.onTap});

  final Supplier supplier;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final hasStock = supplier.totalAvailableStock > 0;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: AppColors.rule),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        supplier.supplierName.isEmpty
                            ? supplier.supplierCode
                            : supplier.supplierName,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 2),
                      Text(
                        supplier.supplierCode,
                        style: const TextStyle(
                          fontSize: 11.5,
                          color: AppColors.textMuted,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        runSpacing: 6,
                        children: [
                          InfoChip(
                            label: '${supplier.productCount} products',
                            icon: Icons.inventory_2_outlined,
                          ),
                          InfoChip(
                            label: '${supplier.availableCount} in stock',
                            icon: Icons.check_circle_outline_rounded,
                            color: hasStock
                                ? AppColors.success
                                : AppColors.textMuted,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                const Icon(
                  Icons.chevron_right_rounded,
                  size: 20,
                  color: AppColors.textMuted,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SupplierDetailSheet extends StatelessWidget {
  const _SupplierDetailSheet({required this.supplier});

  final Supplier supplier;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            supplier.supplierName.isEmpty
                ? supplier.supplierCode
                : supplier.supplierName,
            style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 4),
          Text(
            supplier.supplierCode,
            style: const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
          ),
          const SizedBox(height: 16),
          MetricRow(
            tiles: [
              MetricTile(
                label: 'Products',
                value: '${supplier.productCount}',
                icon: Icons.inventory_2_outlined,
                color: AppColors.accent,
              ),
              MetricTile(
                label: 'In stock',
                value: '${supplier.availableCount}',
                icon: Icons.check_circle_outline_rounded,
                color: AppColors.success,
              ),
              MetricTile(
                label: 'Units',
                value: _compact(supplier.totalAvailableStock),
                icon: Icons.numbers_rounded,
                color: AppColors.info,
                width: 104,
              ),
            ],
          ),
          const SizedBox(height: 18),
          const Divider(height: 1),
          const SizedBox(height: 8),
          InfoRow(
            label: 'Status',
            value: supplier.isActive ? 'Active' : 'Inactive',
          ),
          InfoRow(
            label: 'Stock imported',
            value: formatRelative(supplier.lastImportedAt),
          ),
          InfoRow(
            label: 'Cached on device',
            value: formatRelative(supplier.syncedAt),
          ),
          if (supplier.version != null)
            InfoRow(label: 'Version', value: '${supplier.version}'),
        ],
      ),
    );
  }

  static String _compact(double n) {
    if (n < 1000) return n.round().toString();
    if (n < 1000000) return '${(n / 1000).toStringAsFixed(1)}k';
    return '${(n / 1000000).toStringAsFixed(1)}M';
  }
}

class _Scrollable extends StatelessWidget {
  const _Scrollable({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: Center(
            child: Padding(padding: const EdgeInsets.all(32), child: child),
          ),
        ),
      ),
    );
  }
}
