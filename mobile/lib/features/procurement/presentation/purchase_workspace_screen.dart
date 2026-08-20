import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/error_view.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/core/widgets/offline_banner.dart';
import 'package:nexora_mobile/features/procurement/application/purchase_workspace_providers.dart';
import 'package:nexora_mobile/features/procurement/domain/purchase_workspace_models.dart';

class PurchaseWorkspaceScreen extends ConsumerStatefulWidget {
  const PurchaseWorkspaceScreen({super.key});

  @override
  ConsumerState<PurchaseWorkspaceScreen> createState() =>
      _PurchaseWorkspaceScreenState();
}

class _PurchaseWorkspaceScreenState
    extends ConsumerState<PurchaseWorkspaceScreen> {
  final _searchController = TextEditingController();
  final _localItems = <String, PurchaseWorkspaceItem>{};
  String _search = '';
  String? _busyItemId;

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final workspace = ref.watch(purchaseWorkspaceProvider(_search));
    return Scaffold(
      appBar: AppBar(title: const Text('Purchase Workspace')),
      body: Column(
        children: [
          const OfflineBanner(
            message: 'Offline edits are kept on this device and sent later.',
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: TextField(
              controller: _searchController,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                hintText: 'Search product name or code',
                prefixIcon: const Icon(Icons.search_rounded),
                suffixIcon: _search.isEmpty
                    ? null
                    : IconButton(
                        tooltip: 'Clear search',
                        onPressed: () {
                          _searchController.clear();
                          setState(() => _search = '');
                        },
                        icon: const Icon(Icons.close_rounded),
                      ),
              ),
              onSubmitted: (value) => setState(() => _search = value.trim()),
            ),
          ),
          Expanded(
            child: workspace.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => ErrorView(
                message: error is ApiException
                    ? error.message
                    : 'Could not load the purchase workspace.',
                onRetry: () =>
                    ref.invalidate(purchaseWorkspaceProvider(_search)),
              ),
              data: (data) {
                if (data == null) {
                  return const Center(
                    child: EmptyState(
                      icon: Icons.playlist_add_check_circle_outlined,
                      message: 'Start a refresh in Cycle Console first.',
                    ),
                  );
                }
                final items = data.page.items
                    .map((item) => _localItems[item.orderItemId] ?? item)
                    .toList(growable: false);
                if (items.isEmpty) {
                  return const Center(
                    child: EmptyState(
                      icon: Icons.search_off_rounded,
                      message: 'No products match this search.',
                    ),
                  );
                }
                return RefreshIndicator(
                  onRefresh: () async {
                    _localItems.clear();
                    ref.invalidate(purchaseWorkspaceProvider(_search));
                    await ref.read(purchaseWorkspaceProvider(_search).future);
                  },
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                    children: [
                      MetricRow(
                        tiles: [
                          MetricTile(
                            label: 'Products',
                            value: data.page.total.toString(),
                            icon: Icons.medication_outlined,
                            color: AppColors.accent,
                          ),
                          MetricTile(
                            label: 'Shown',
                            value: items.length.toString(),
                            icon: Icons.view_agenda_outlined,
                            color: AppColors.info,
                          ),
                          MetricTile(
                            label: 'To assign',
                            value: items
                                .where((item) => item.canAssign)
                                .length
                                .toString(),
                            icon: Icons.local_shipping_outlined,
                            color: AppColors.warning,
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      for (final item in items)
                        _ProductCard(
                          item: item,
                          busy: _busyItemId == item.orderItemId,
                          onEditQty: () => _editQuantity(data.context, item),
                          onAssign: item.canAssign
                              ? () => _assignSupplier(data.context, item)
                              : null,
                          onToggleSkip: () => _toggleSkip(data.context, item),
                        ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _editQuantity(
    PurchaseWorkspaceContext workspace,
    PurchaseWorkspaceItem item,
  ) async {
    final controller = TextEditingController(text: item.finalQty.compact);
    final qty = await showDialog<double>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(item.productName),
        content: TextField(
          controller: controller,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: 'Final quantity',
            helperText: 'Suggested: ${item.suggestedQty.compact}',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              dialogContext,
              double.tryParse(controller.text.trim()),
            ),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (qty == null || qty < 0) return;
    await _runItemAction(
      item,
      () => ref.read(purchaseWorkspaceControllerProvider).setFinalQty(
            context: workspace,
            item: item,
            qty: qty,
          ),
    );
  }

  Future<void> _assignSupplier(
    PurchaseWorkspaceContext workspace,
    PurchaseWorkspaceItem item,
  ) async {
    final supplier = await showModalBottomSheet<PurchaseSupplier>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _SupplierPicker(context: workspace),
    );
    if (supplier == null || !mounted) return;
    final quantityController =
        TextEditingController(text: item.remainingQty.compact);
    final qty = await showDialog<double>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text('Assign to ${supplier.name}'),
        content: TextField(
          controller: quantityController,
          autofocus: true,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: 'Assignment quantity',
            helperText: '${item.remainingQty.compact} remaining',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              dialogContext,
              double.tryParse(quantityController.text.trim()),
            ),
            child: const Text('Assign'),
          ),
        ],
      ),
    );
    quantityController.dispose();
    if (qty == null) return;
    await _runItemAction(
      item,
      () => ref.read(purchaseWorkspaceControllerProvider).assign(
            context: workspace,
            item: item,
            supplier: supplier,
            qty: qty,
          ),
    );
  }

  Future<void> _toggleSkip(
    PurchaseWorkspaceContext workspace,
    PurchaseWorkspaceItem item,
  ) async {
    final controller = ref.read(purchaseWorkspaceControllerProvider);
    if (item.status == 'skipped') {
      await _runItemAction(
        item,
        () => controller.restore(context: workspace, item: item),
      );
      return;
    }
    final reasonController = TextEditingController();
    final reason = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Skip this product?'),
        content: TextField(
          controller: reasonController,
          autofocus: true,
          maxLength: 300,
          decoration: const InputDecoration(labelText: 'Reason'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              final value = reasonController.text.trim();
              if (value.isNotEmpty) Navigator.pop(dialogContext, value);
            },
            child: const Text('Skip'),
          ),
        ],
      ),
    );
    reasonController.dispose();
    if (reason == null) return;
    await _runItemAction(
      item,
      () => controller.skip(context: workspace, item: item, reason: reason),
    );
  }

  Future<void> _runItemAction(
    PurchaseWorkspaceItem item,
    Future<PurchaseActionResult> Function() action,
  ) async {
    setState(() => _busyItemId = item.orderItemId);
    final result = await action();
    if (!mounted) return;
    setState(() {
      _busyItemId = null;
      if (result.item != null) _localItems[item.orderItemId] = result.item!;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({
    required this.item,
    required this.busy,
    required this.onEditQty,
    required this.onAssign,
    required this.onToggleSkip,
  });

  final PurchaseWorkspaceItem item;
  final bool busy;
  final VoidCallback onEditQty;
  final VoidCallback? onAssign;
  final VoidCallback onToggleSkip;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item.productName,
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 3),
                      Text(
                        [item.productCode, item.unitDescription, item.pack]
                            .whereType<String>()
                            .where((value) => value.isNotEmpty)
                            .join(' · '),
                        style: const TextStyle(
                          fontSize: 12,
                          color: AppColors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
                StatusBadge(
                  label: item.status,
                  color: item.status == 'assigned'
                      ? AppColors.success
                      : item.status == 'skipped'
                          ? AppColors.textMuted
                          : AppColors.warning,
                  dense: true,
                ),
                PopupMenuButton<String>(
                  tooltip: 'More actions',
                  onSelected: (_) => onToggleSkip(),
                  itemBuilder: (_) => [
                    PopupMenuItem(
                      value: 'toggle-skip',
                      child:
                          Text(item.status == 'skipped' ? 'Restore' : 'Skip'),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                InfoChip(label: 'Suggested ${item.suggestedQty.compact}'),
                InfoChip(
                  label: 'Final ${item.finalQty.compact}',
                  color: AppColors.accentInk,
                ),
                InfoChip(
                  label: 'Remaining ${item.remainingQty.compact}',
                  color: item.remainingQty > 0
                      ? AppColors.warningInk
                      : AppColors.successInk,
                ),
                if (item.movementClass != null)
                  InfoChip(label: item.movementClass!),
              ],
            ),
            const SizedBox(height: 12),
            if (busy)
              const LinearProgressIndicator()
            else
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      child: OutlinedButton.icon(
                        onPressed: onEditQty,
                        icon: const Icon(Icons.edit_outlined, size: 17),
                        label: const Text('Quantity'),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: SizedBox(
                      child: FilledButton.icon(
                        onPressed: onAssign,
                        icon:
                            const Icon(Icons.local_shipping_outlined, size: 17),
                        label: const Text('Assign'),
                      ),
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

class _SupplierPicker extends ConsumerStatefulWidget {
  const _SupplierPicker({required this.context});

  final PurchaseWorkspaceContext context;

  @override
  ConsumerState<_SupplierPicker> createState() => _SupplierPickerState();
}

class _SupplierPickerState extends ConsumerState<_SupplierPicker> {
  final _controller = TextEditingController();
  late Future<List<PurchaseSupplier>> _results;

  @override
  void initState() {
    super.initState();
    _results = _search('');
  }

  Future<List<PurchaseSupplier>> _search(String query) =>
      ref.read(purchaseWorkspaceApiProvider).suppliers(
            tenantId: widget.context.tenantId,
            storeId: widget.context.storeId,
            query: query,
          );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          16,
          16,
          16,
          MediaQuery.viewInsetsOf(context).bottom + 16,
        ),
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height * .62,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Choose supplier',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
              const SizedBox(height: 12),
              TextField(
                controller: _controller,
                autofocus: true,
                textInputAction: TextInputAction.search,
                decoration: const InputDecoration(
                  hintText: 'Search supplier',
                  prefixIcon: Icon(Icons.search_rounded),
                ),
                onSubmitted: (query) =>
                    setState(() => _results = _search(query)),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: FutureBuilder<List<PurchaseSupplier>>(
                  future: _results,
                  builder: (_, snapshot) {
                    if (snapshot.connectionState != ConnectionState.done) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    if (snapshot.hasError) {
                      return const Center(
                          child: Text('Could not load suppliers.'));
                    }
                    final suppliers = snapshot.data ?? const [];
                    if (suppliers.isEmpty) {
                      return const Center(child: Text('No suppliers found.'));
                    }
                    return ListView.builder(
                      itemCount: suppliers.length,
                      itemBuilder: (_, index) {
                        final supplier = suppliers[index];
                        return ListTile(
                          title: Text(supplier.name),
                          subtitle: Text(supplier.code),
                          trailing: const Icon(Icons.chevron_right_rounded),
                          onTap: () => Navigator.pop(context, supplier),
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

extension on double {
  String get compact =>
      this == roundToDouble() ? toInt().toString() : toString();
}
