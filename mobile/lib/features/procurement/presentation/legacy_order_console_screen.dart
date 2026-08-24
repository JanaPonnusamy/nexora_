import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/error_view.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/core/widgets/offline_banner.dart';
import 'package:nexora_mobile/features/procurement/application/legacy_order_providers.dart';
import 'package:nexora_mobile/features/procurement/domain/legacy_order_models.dart';

/// Field-sized control surface for the old OrderNMC workflow.
///
/// It deliberately omits line-by-line order editing and database repair. The
/// phone covers the actions that block a store: check health, run and watch a
/// job, then review the small Qty Check queue with its evidence drill-downs.
class LegacyOrderConsoleScreen extends ConsumerStatefulWidget {
  const LegacyOrderConsoleScreen({super.key});

  @override
  ConsumerState<LegacyOrderConsoleScreen> createState() =>
      _LegacyOrderConsoleScreenState();
}

class _LegacyOrderConsoleScreenState
    extends ConsumerState<LegacyOrderConsoleScreen> {
  final _log = AppLogger.of('LegacyOrderConsole');
  Timer? _poller;
  String? _storeName;
  String _qtyMode = 'local';
  bool _busy = false;

  @override
  void dispose() {
    _poller?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final console = ref.watch(legacyConsoleProvider);
    final data = console.asData?.value;
    final selected = data == null ? null : _selectedStore(data.stores);
    final health = ref.watch(legacyHealthProvider);

    ref.listen(legacyConsoleProvider, (_, next) {
      next.whenData((data) => _setPolling(data.hasRunningJobs));
    });

    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Legacy Order'),
          bottom: const TabBar(
            tabs: [
              Tab(text: 'Operations'),
              Tab(text: 'Qty check'),
              Tab(text: 'Compare'),
            ],
          ),
          actions: [
            IconButton(
              tooltip: 'Refresh',
              onPressed: _refresh,
              icon: const Icon(Icons.refresh_rounded),
            ),
          ],
        ),
        body: Column(
          children: [
            const OfflineBanner(
              message: 'Offline — Legacy Order needs the HO connection.',
            ),
            Expanded(
              child: TabBarView(
                children: [
                  if (data == null)
                    _OperationsUnavailable(
                      health: health,
                      loading: console.isLoading,
                      error: console.error,
                      onRetry: _refresh,
                      onHealthRefresh: () =>
                          ref.invalidate(legacyHealthProvider),
                    )
                  else
                    _OperationsTab(
                      data: data,
                      selectedStore: selected,
                      busy: _busy,
                      onStoreChanged: (value) =>
                          setState(() => _storeName = value),
                      onSync:
                          selected == null ? null : () => _startSync(selected),
                      onOrder: selected == null
                          ? null
                          : () => _startOrder(selected, data.defaults),
                      onStock: selected == null || selected.name == 'NMW'
                          ? null
                          : () => _startStock(selected),
                      health: health,
                      onHealthRefresh: () =>
                          ref.invalidate(legacyHealthProvider),
                    ),
                  if (data == null)
                    console.isLoading
                        ? const Center(child: CircularProgressIndicator())
                        : ErrorView(
                            message: _message(
                              console.error ??
                                  const ApiException(
                                    message: 'Could not load Legacy Order.',
                                  ),
                              'Could not load Legacy Order.',
                            ),
                            onRetry: _refresh,
                          )
                  else
                    _QtyCheckTab(
                      stores: data.stores,
                      selectedStore: selected,
                      mode: _qtyMode,
                      busy: _busy,
                      onStoreChanged: (value) =>
                          setState(() => _storeName = value),
                      onModeChanged: (value) =>
                          setState(() => _qtyMode = value),
                      onReview: selected == null
                          ? null
                          : (row) => _reviewQty(selected, row),
                      onDetails: selected == null
                          ? null
                          : (row) => _showDetails(selected, row),
                    ),
                  if (data == null)
                    console.isLoading
                        ? const Center(child: CircularProgressIndicator())
                        : ErrorView(
                            message: _message(
                              console.error ??
                                  const ApiException(
                                    message: 'Could not load Legacy Order.',
                                  ),
                              'Could not load Legacy Order.',
                            ),
                            onRetry: _refresh,
                          )
                  else
                    _PreviousOrderTab(
                      stores: data.stores,
                      selectedStore: selected,
                      busy: _busy ||
                          data.jobs.any(
                            (job) =>
                                job.isRunning &&
                                job.storeName == selected?.name,
                          ),
                      onStoreChanged: (value) =>
                          setState(() => _storeName = value),
                      onCompare: selected == null
                          ? null
                          : (order) => _comparePreviousOrder(selected, order),
                      onReviewSupplier: selected == null
                          ? null
                          : (order, supplier) => _showSupplierComparison(
                                selected,
                                order,
                                supplier,
                              ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  LegacyStore? _selectedStore(List<LegacyStore> stores) {
    if (stores.isEmpty) return null;
    for (final store in stores) {
      if (store.name == _storeName) return store;
    }
    return stores.first;
  }

  void _setPolling(bool needed) {
    if (!needed) {
      _poller?.cancel();
      _poller = null;
      return;
    }
    _poller ??= Timer.periodic(const Duration(seconds: 2), (_) {
      ref.invalidate(legacyConsoleProvider);
    });
  }

  void _refresh() {
    ref.invalidate(legacyHealthProvider);
    ref.invalidate(legacyConsoleProvider);
    final store = _storeName;
    if (store != null) ref.invalidate(qtyCheckRowsProvider(store));
  }

  Future<T?> _guard<T>(Future<T> Function() action) async {
    setState(() => _busy = true);
    try {
      return await action();
    } on ApiException catch (error) {
      _log.warning('Legacy Order action failed: ${error.message}');
      _say(error.isNetwork
          ? 'Cannot reach the server. Nothing was changed.'
          : error.message);
      return null;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _startSync(LegacyStore store) async {
    if (!await _confirm(
      title: 'Sync ${store.name}?',
      body: 'This refreshes every legacy table from the branch database. The '
          'job keeps running on the server if you leave this screen.',
      label: 'Start sync',
    )) {
      return;
    }
    final id = await _guard(
      () => ref.read(legacyOrderApiProvider).startSync(store.name),
    );
    if (id == null) return;
    _setPolling(true);
    ref.invalidate(legacyConsoleProvider);
    _say('Sync started for ${store.name}.');
  }

  Future<void> _startOrder(
    LegacyStore store,
    LegacyDefaults defaults,
  ) async {
    final settings = await showModalBottomSheet<_OrderSettings>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _OrderSettingsSheet(defaults: defaults),
    );
    if (settings == null) return;

    final id = await _guard(
      () => ref.read(legacyOrderApiProvider).startOrderProcess(
            storeName: store.name,
            minDays: settings.minDays,
            maxDays: settings.maxDays,
            mode: settings.mode,
          ),
    );
    if (id == null) return;
    _setPolling(true);
    ref.invalidate(legacyConsoleProvider);
    _say('Order process started for ${store.name}.');
  }

  Future<void> _startStock(LegacyStore store) async {
    if (!await _confirm(
      title: 'Update ${store.name} stock?',
      body: 'This replaces the store’s NMW supplier-stock rows with the '
          'current NMW branch stock.',
      label: 'Start update',
    )) {
      return;
    }
    final id = await _guard(
      () => ref.read(legacyOrderApiProvider).startStockUpdate(store.name),
    );
    if (id == null) return;
    _setPolling(true);
    ref.invalidate(legacyConsoleProvider);
    _say('Stock update started for ${store.name}.');
  }

  Future<PreviousOrderComparison?> _comparePreviousOrder(
    LegacyStore store,
    PreviousOrder order,
  ) async {
    if (!await _confirm(
      title: 'Compare order #${order.orderId}?',
      body: 'This applies the original Legacy Order comparison rules to the '
          'current ${store.name} order. Matching quantities, suppliers and '
          'statuses can be updated.',
      label: 'Compare order',
    )) {
      return null;
    }
    final result = await _guard(
      () => ref.read(legacyOrderApiProvider).comparePreviousOrder(
            storeName: store.name,
            orderId: order.orderId,
          ),
    );
    if (result == null) return null;
    ref.invalidate(qtyCheckRowsProvider(store.name));
    _say(
      'Compared order #${result.orderId}. '
      '${result.affectedRows} row updates applied.',
    );
    return result;
  }

  Future<void> _showSupplierComparison(
    LegacyStore store,
    PreviousOrder order,
    PreviousOrderSupplier supplier,
  ) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => _SupplierComparisonSheet(
        request: SupplierComparisonRequest(
          storeName: store.name,
          orderId: order.orderId,
          supplierCode: supplier.code,
        ),
        supplier: supplier,
        onCompare: () => _comparePreviousOrderSupplier(
          store,
          order,
          supplier,
        ),
      ),
    );
  }

  Future<PreviousOrderComparison?> _comparePreviousOrderSupplier(
    LegacyStore store,
    PreviousOrder order,
    PreviousOrderSupplier supplier,
  ) async {
    if (!await _confirm(
      title: 'Compare ${supplier.name}?',
      body: 'This applies order #${order.orderId} only for this supplier and '
          'updates matching current-order rows.',
      label: 'Compare supplier',
    )) {
      return null;
    }
    final result = await _guard(
      () => ref.read(legacyOrderApiProvider).comparePreviousOrderSupplier(
            storeName: store.name,
            orderId: order.orderId,
            supplierCode: supplier.code,
          ),
    );
    if (result == null) return null;
    ref.invalidate(qtyCheckRowsProvider(store.name));
    ref.invalidate(
      supplierComparisonProductsProvider(
        SupplierComparisonRequest(
          storeName: store.name,
          orderId: order.orderId,
          supplierCode: supplier.code,
        ),
      ),
    );
    _say(
      'Compared ${supplier.name}. '
      '${result.affectedRows} row updates applied.',
    );
    return result;
  }

  Future<void> _reviewQty(LegacyStore store, QtyCheckRow row) async {
    final controller = TextEditingController(text: row.orderQty.toString());
    final quantity = await showDialog<int>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(row.productName),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
                'Current stock ${_num(row.totalStock)} · Suggested ${row.orderQty}'),
            const SizedBox(height: 16),
            TextField(
              controller: controller,
              autofocus: true,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Reviewed order quantity',
                helperText: 'Use 0 for “Don’t want to order”.',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              final value = int.tryParse(controller.text.trim());
              if (value == null || value < 0) return;
              Navigator.of(dialogContext).pop(value);
            },
            child: const Text('Mark reviewed'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (quantity == null) return;

    final remark = await _guard(
      () => ref.read(legacyOrderApiProvider).updateQtyCheck(
            storeName: store.name,
            productCode: row.productCode,
            orderQty: quantity,
          ),
    );
    if (remark == null) return;
    ref.invalidate(qtyCheckRowsProvider(store.name));
    _say(remark);
  }

  Future<void> _showDetails(LegacyStore store, QtyCheckRow row) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (_) => _QtyDetailsSheet(
        row: row,
        request: QtyCheckRequest(
          storeName: store.name,
          productCode: row.productCode,
          mode: _qtyMode,
        ),
      ),
    );
  }

  Future<bool> _confirm({
    required String title,
    required String body,
    required String label,
  }) async {
    return await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: Text(title),
            content: Text(body),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: const Text('Cancel'),
              ),
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: Text(label),
              ),
            ],
          ),
        ) ??
        false;
  }

  void _say(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}

class _OperationsTab extends StatelessWidget {
  const _OperationsTab({
    required this.data,
    required this.selectedStore,
    required this.busy,
    required this.onStoreChanged,
    required this.onSync,
    required this.onOrder,
    required this.onStock,
    required this.health,
    required this.onHealthRefresh,
  });

  final LegacyConsoleData data;
  final LegacyStore? selectedStore;
  final bool busy;
  final ValueChanged<String?> onStoreChanged;
  final VoidCallback? onSync;
  final VoidCallback? onOrder;
  final VoidCallback? onStock;
  final AsyncValue<LegacyDbHealth> health;
  final VoidCallback onHealthRefresh;

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => onHealthRefresh(),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
        children: [
          const SectionHeader(
            title: 'ORDERNMC DATABASE',
            icon: Icons.dns_outlined,
          ),
          _HealthState(health: health, onRefresh: onHealthRefresh),
          const SizedBox(height: 18),
          SectionHeader(
            title: 'STORE OPERATIONS',
            icon: Icons.storefront_outlined,
            trailing: InfoChip(
              label: '${data.stores.length} stores',
              color: AppColors.accent,
            ),
          ),
          if (data.stores.isEmpty)
            const EmptyState(
              icon: Icons.store_mall_directory_outlined,
              message: 'No active legacy stores are configured.',
            )
          else ...[
            DropdownButtonFormField<String>(
              initialValue: selectedStore?.name,
              decoration: const InputDecoration(labelText: 'Legacy store'),
              items: [
                for (final store in data.stores)
                  DropdownMenuItem(value: store.name, child: Text(store.name)),
              ],
              onChanged: busy ? null : onStoreChanged,
            ),
            const SizedBox(height: 12),
            if (selectedStore != null) _StoreCard(store: selectedStore!),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                FilledButton.icon(
                  style: FilledButton.styleFrom(minimumSize: const Size(0, 44)),
                  onPressed: busy ? null : onSync,
                  icon: const Icon(Icons.sync_rounded),
                  label: const Text('Sync'),
                ),
                OutlinedButton.icon(
                  style:
                      OutlinedButton.styleFrom(minimumSize: const Size(0, 44)),
                  onPressed: busy ? null : onOrder,
                  icon: const Icon(Icons.playlist_add_check_rounded),
                  label: const Text('Order process'),
                ),
                OutlinedButton.icon(
                  style:
                      OutlinedButton.styleFrom(minimumSize: const Size(0, 44)),
                  onPressed: busy ? null : onStock,
                  icon: const Icon(Icons.inventory_2_outlined),
                  label: const Text('Stock update'),
                ),
              ],
            ),
            if (selectedStore?.name == 'NMW') ...[
              const SizedBox(height: 8),
              const Text(
                'NMW is the stock source, so it cannot update itself.',
                style: TextStyle(fontSize: 12, color: AppColors.textMuted),
              ),
            ],
          ],
          const SizedBox(height: 22),
          SectionHeader(
            title: 'RECENT JOBS',
            icon: Icons.manage_history_rounded,
            trailing: data.hasRunningJobs
                ? const InfoChip(
                    label: 'Live',
                    icon: Icons.circle,
                    color: AppColors.info,
                  )
                : null,
          ),
          if (data.jobs.isEmpty)
            const EmptyState(
              icon: Icons.history_toggle_off_rounded,
              message: 'No jobs have run since the server started.',
            )
          else
            for (final job in data.jobs) _JobCard(job: job),
        ],
      ),
    );
  }
}

class _OperationsUnavailable extends StatelessWidget {
  const _OperationsUnavailable({
    required this.health,
    required this.loading,
    required this.error,
    required this.onRetry,
    required this.onHealthRefresh,
  });

  final AsyncValue<LegacyDbHealth> health;
  final bool loading;
  final Object? error;
  final VoidCallback onRetry;
  final VoidCallback onHealthRefresh;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
      children: [
        const SectionHeader(
          title: 'ORDERNMC DATABASE',
          icon: Icons.dns_outlined,
        ),
        _HealthState(health: health, onRefresh: onHealthRefresh),
        const SizedBox(height: 18),
        const SectionHeader(
          title: 'STORE OPERATIONS',
          icon: Icons.storefront_outlined,
        ),
        if (loading)
          const Padding(
            padding: EdgeInsets.all(32),
            child: Center(child: CircularProgressIndicator()),
          )
        else
          Card(
            child: ListTile(
              leading: const Icon(Icons.error_outline, color: AppColors.danger),
              title: const Text('Store operations unavailable'),
              subtitle: Text(
                _message(error ?? Object(), 'Could not load legacy stores.'),
              ),
              trailing: IconButton(
                tooltip: 'Retry',
                onPressed: onRetry,
                icon: const Icon(Icons.refresh),
              ),
            ),
          ),
      ],
    );
  }
}

class _PreviousOrderTab extends ConsumerStatefulWidget {
  const _PreviousOrderTab({
    required this.stores,
    required this.selectedStore,
    required this.busy,
    required this.onStoreChanged,
    required this.onCompare,
    required this.onReviewSupplier,
  });

  final List<LegacyStore> stores;
  final LegacyStore? selectedStore;
  final bool busy;
  final ValueChanged<String?> onStoreChanged;
  final Future<PreviousOrderComparison?> Function(PreviousOrder)? onCompare;
  final void Function(PreviousOrder, PreviousOrderSupplier)? onReviewSupplier;

  @override
  ConsumerState<_PreviousOrderTab> createState() => _PreviousOrderTabState();
}

class _PreviousOrderTabState extends ConsumerState<_PreviousOrderTab> {
  int? _selectedOrderId;

  @override
  void didUpdateWidget(covariant _PreviousOrderTab oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.selectedStore?.name != widget.selectedStore?.name) {
      _selectedOrderId = null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final storeName = widget.selectedStore?.name ?? '';
    final orders = ref.watch(previousOrdersProvider(storeName));

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(previousOrdersProvider(storeName)),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
        children: [
          const SectionHeader(
            title: 'COMPARE PREVIOUS ORDER',
            icon: Icons.compare_arrows_rounded,
          ),
          const Text(
            'Uses the original Legacy Order rules. Recent two-day orders are '
            'shown first, with the latest five as fallback.',
            style: TextStyle(fontSize: 12, color: AppColors.textMuted),
          ),
          const SizedBox(height: 14),
          DropdownButtonFormField<String>(
            initialValue: widget.selectedStore?.name,
            decoration: const InputDecoration(labelText: 'Legacy store'),
            items: [
              for (final store in widget.stores)
                DropdownMenuItem(value: store.name, child: Text(store.name)),
            ],
            onChanged: widget.busy ? null : widget.onStoreChanged,
          ),
          const SizedBox(height: 16),
          orders.when(
            loading: () => const Card(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: LinearProgressIndicator(),
              ),
            ),
            error: (error, _) => _CompareErrorCard(
              message: _message(error, 'Could not load previous orders.'),
              onRetry: () => ref.invalidate(previousOrdersProvider(storeName)),
            ),
            data: (values) {
              if (values.isEmpty) {
                return const EmptyState(
                  icon: Icons.receipt_long_outlined,
                  message: 'No previous orders are available for this store.',
                );
              }
              var selected = values.first;
              for (final order in values) {
                if (order.orderId == _selectedOrderId) selected = order;
              }
              return _PreviousOrdersBody(
                orders: values,
                selected: selected,
                busy: widget.busy,
                onSelected: (order) =>
                    setState(() => _selectedOrderId = order.orderId),
                onCompare: widget.onCompare,
                onReviewSupplier: widget.onReviewSupplier,
              );
            },
          ),
        ],
      ),
    );
  }
}

class _PreviousOrdersBody extends ConsumerWidget {
  const _PreviousOrdersBody({
    required this.orders,
    required this.selected,
    required this.busy,
    required this.onSelected,
    required this.onCompare,
    required this.onReviewSupplier,
  });

  final List<PreviousOrder> orders;
  final PreviousOrder selected;
  final bool busy;
  final ValueChanged<PreviousOrder> onSelected;
  final Future<PreviousOrderComparison?> Function(PreviousOrder)? onCompare;
  final void Function(PreviousOrder, PreviousOrderSupplier)? onReviewSupplier;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final request = PreviousOrderRequest(
      storeName: selected.storeName,
      orderId: selected.orderId,
    );
    final suppliers = ref.watch(previousOrderSuppliersProvider(request));

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Previous order',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        const SizedBox(height: 8),
        for (final order in orders)
          Card(
            margin: const EdgeInsets.only(bottom: 8),
            child: ListTile(
              selected: order.orderId == selected.orderId,
              onTap: busy ? null : () => onSelected(order),
              leading: Icon(
                order.orderId == selected.orderId
                    ? Icons.radio_button_checked_rounded
                    : Icons.radio_button_unchecked_rounded,
                color: order.orderId == selected.orderId
                    ? AppColors.accent
                    : AppColors.textMuted,
              ),
              title: Text(
                'Order #${order.orderId}',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
              subtitle: Text(
                order.wantedAt == null
                    ? 'Date unavailable'
                    : _dateTime(order.wantedAt),
              ),
            ),
          ),
        const SizedBox(height: 4),
        FilledButton.icon(
          onPressed:
              busy || onCompare == null ? null : () => onCompare!(selected),
          icon: const Icon(Icons.compare_arrows_rounded),
          label: Text('Compare entire order #${selected.orderId}'),
        ),
        const SizedBox(height: 20),
        SectionHeader(
          title: 'SUPPLIERS IN ORDER #${selected.orderId}',
          icon: Icons.local_shipping_outlined,
        ),
        suppliers.when(
          loading: () => const Padding(
            padding: EdgeInsets.all(20),
            child: Center(child: CircularProgressIndicator()),
          ),
          error: (error, _) => _CompareErrorCard(
            message: _message(error, 'Could not load order suppliers.'),
            onRetry: () =>
                ref.invalidate(previousOrderSuppliersProvider(request)),
          ),
          data: (values) => values.isEmpty
              ? const EmptyState(
                  icon: Icons.inventory_2_outlined,
                  message: 'No assigned suppliers in this backup order.',
                )
              : Column(
                  children: [
                    for (final supplier in values)
                      ActionTile(
                        title: supplier.name,
                        subtitle:
                            '${supplier.code} · ${supplier.productCount} products',
                        icon: Icons.local_shipping_outlined,
                        trailing: const Icon(Icons.chevron_right_rounded),
                        onTap: busy || onReviewSupplier == null
                            ? null
                            : () => onReviewSupplier!(selected, supplier),
                      ),
                  ],
                ),
        ),
      ],
    );
  }
}

class _CompareErrorCard extends StatelessWidget {
  const _CompareErrorCard({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.error_outline, color: AppColors.danger),
        title: Text(message),
        trailing: IconButton(
          tooltip: 'Retry',
          onPressed: onRetry,
          icon: const Icon(Icons.refresh_rounded),
        ),
      ),
    );
  }
}

class _SupplierComparisonSheet extends ConsumerStatefulWidget {
  const _SupplierComparisonSheet({
    required this.request,
    required this.supplier,
    required this.onCompare,
  });

  final SupplierComparisonRequest request;
  final PreviousOrderSupplier supplier;
  final Future<PreviousOrderComparison?> Function() onCompare;

  @override
  ConsumerState<_SupplierComparisonSheet> createState() =>
      _SupplierComparisonSheetState();
}

class _SupplierComparisonSheetState
    extends ConsumerState<_SupplierComparisonSheet> {
  bool _applying = false;

  @override
  Widget build(BuildContext context) {
    final products =
        ref.watch(supplierComparisonProductsProvider(widget.request));
    final loadedProducts = products.asData?.value;

    return FractionallySizedBox(
      heightFactor: 0.92,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 12, 12),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.supplier.name,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      Text(
                        'Order #${widget.request.orderId} · '
                        '${widget.supplier.productCount} products',
                        style: const TextStyle(color: AppColors.textMuted),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Close',
                  onPressed:
                      _applying ? null : () => Navigator.of(context).pop(),
                  icon: const Icon(Icons.close_rounded),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: products.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => ErrorView(
                message: _message(
                  error,
                  'Could not load the supplier comparison.',
                ),
                onRetry: () => ref.invalidate(
                  supplierComparisonProductsProvider(widget.request),
                ),
              ),
              data: (values) => values.isEmpty
                  ? const EmptyState(
                      icon: Icons.inventory_2_outlined,
                      message: 'No products are available for review.',
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: values.length,
                      itemBuilder: (_, index) =>
                          _ComparisonProductCard(product: values[index]),
                    ),
            ),
          ),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: _applying || loadedProducts?.isEmpty != false
                      ? null
                      : _apply,
                  icon: _applying
                      ? const SizedBox.square(
                          dimension: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.compare_arrows_rounded),
                  label: Text(
                    _applying
                        ? 'Comparing…'
                        : 'Compare ${loadedProducts?.length ?? 0} products',
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _apply() async {
    setState(() => _applying = true);
    final result = await widget.onCompare();
    if (!mounted) return;
    setState(() => _applying = false);
    if (result != null) Navigator.of(context).pop();
  }
}

class _ComparisonProductCard extends StatelessWidget {
  const _ComparisonProductCard({required this.product});

  final SupplierComparisonProduct product;

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
              children: [
                Expanded(
                  child: Text(
                    product.productName,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                StatusBadge(
                  label: product.changed ? 'Changed' : 'Same',
                  color:
                      product.changed ? AppColors.warning : AppColors.success,
                  dense: true,
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              'Product ${product.previousProductCode}',
              style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _CompareValue(
                    label: 'Previous qty',
                    value: _num(product.previousOrderedQty),
                  ),
                ),
                Expanded(
                  child: _CompareValue(
                    label: 'Current qty',
                    value: _num(product.currentOrderQty),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              children: [
                Expanded(
                  child: _CompareValue(
                    label: 'Previous stock',
                    value: _num(product.previousStock),
                  ),
                ),
                Expanded(
                  child: _CompareValue(
                    label: 'Current stock',
                    value: _num(product.currentStock),
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

class _CompareValue extends StatelessWidget {
  const _CompareValue({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 11, color: AppColors.textMuted),
        ),
        const SizedBox(height: 2),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w700)),
      ],
    );
  }
}

class _HealthState extends StatelessWidget {
  const _HealthState({required this.health, required this.onRefresh});

  final AsyncValue<LegacyDbHealth> health;
  final VoidCallback onRefresh;

  @override
  Widget build(BuildContext context) {
    return health.when(
      loading: () => const Card(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: LinearProgressIndicator(),
        ),
      ),
      error: (error, _) => Card(
        child: ListTile(
          leading: const Icon(Icons.error_outline, color: AppColors.danger),
          title: const Text('Health check failed'),
          subtitle: Text(_message(error, 'Could not check OrderNMC.')),
          trailing: IconButton(
            tooltip: 'Recheck',
            onPressed: onRefresh,
            icon: const Icon(Icons.refresh),
          ),
        ),
      ),
      data: (value) => _HealthCard(health: value),
    );
  }
}

class _HealthCard extends StatelessWidget {
  const _HealthCard({required this.health});

  final LegacyDbHealth health;

  @override
  Widget build(BuildContext context) {
    final color = health.online ? AppColors.success : AppColors.danger;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    health.database,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                StatusBadge(
                  label: health.online ? 'Online' : 'Needs attention',
                  color: color,
                  dense: true,
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(health.message),
            if (health.state != null || health.access != null) ...[
              const SizedBox(height: 8),
              Text(
                [health.state, health.access].whereType<String>().join(' · '),
                style:
                    const TextStyle(fontSize: 12, color: AppColors.textMuted),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StoreCard extends StatelessWidget {
  const _StoreCard({required this.store});

  final LegacyStore store;

  @override
  Widget build(BuildContext context) {
    final color = store.lastSyncFailed
        ? AppColors.danger
        : store.lastSyncSucceeded
            ? AppColors.success
            : AppColors.textMuted;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    store.name,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                StatusBadge(
                  label: store.lastSyncStatus ?? 'Never synced',
                  color: color,
                  dense: true,
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text('${store.server} · ${store.database}'),
            const SizedBox(height: 4),
            Text(
              store.lastSyncAt == null
                  ? 'No sync timestamp'
                  : 'Last sync ${_dateTime(store.lastSyncAt)}',
              style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
            ),
          ],
        ),
      ),
    );
  }
}

class _JobCard extends StatelessWidget {
  const _JobCard({required this.job});

  final LegacyJob job;

  @override
  Widget build(BuildContext context) {
    final color = switch (job.status) {
      LegacyJobStatus.running => AppColors.info,
      LegacyJobStatus.completed => AppColors.success,
      LegacyJobStatus.failed => AppColors.danger,
      LegacyJobStatus.unknown => AppColors.textMuted,
    };
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${job.storeName} · ${job.kind.label}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                StatusBadge(label: job.statusLabel, color: color, dense: true),
              ],
            ),
            const SizedBox(height: 12),
            LinearProgressIndicator(
              value: job.isRunning && job.totalSteps == 0 ? null : job.progress,
              color: color,
            ),
            const SizedBox(height: 10),
            Text(job.message.isEmpty ? 'No progress message.' : job.message),
            if (job.error != null) ...[
              const SizedBox(height: 6),
              Text(job.error!,
                  style: const TextStyle(color: AppColors.dangerInk)),
            ],
            if (job.log.isNotEmpty) ...[
              const SizedBox(height: 4),
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                childrenPadding: EdgeInsets.zero,
                title: Text('${job.log.length} log entries'),
                children: [
                  for (final entry in job.log.reversed.take(8))
                    ListTile(
                      dense: true,
                      contentPadding: EdgeInsets.zero,
                      title: Text(entry.message),
                      subtitle:
                          entry.at == null ? null : Text(_dateTime(entry.at)),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _QtyCheckTab extends ConsumerWidget {
  const _QtyCheckTab({
    required this.stores,
    required this.selectedStore,
    required this.mode,
    required this.busy,
    required this.onStoreChanged,
    required this.onModeChanged,
    required this.onReview,
    required this.onDetails,
  });

  final List<LegacyStore> stores;
  final LegacyStore? selectedStore;
  final String mode;
  final bool busy;
  final ValueChanged<String?> onStoreChanged;
  final ValueChanged<String> onModeChanged;
  final ValueChanged<QtyCheckRow>? onReview;
  final ValueChanged<QtyCheckRow>? onDetails;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final storeName = selectedStore?.name ?? '';
    final rows = ref.watch(qtyCheckRowsProvider(storeName));

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Column(
            children: [
              DropdownButtonFormField<String>(
                initialValue: selectedStore?.name,
                decoration: const InputDecoration(labelText: 'Legacy store'),
                items: [
                  for (final store in stores)
                    DropdownMenuItem(
                        value: store.name, child: Text(store.name)),
                ],
                onChanged: busy ? null : onStoreChanged,
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 4,
                children: [
                  ChoiceChip(
                    label: const Text('Local copy'),
                    selected: mode == 'local',
                    onSelected: (_) => onModeChanged('local'),
                  ),
                  ChoiceChip(
                    label: const Text('Live branch'),
                    selected: mode == 'remote',
                    onSelected: (_) => onModeChanged('remote'),
                  ),
                ],
              ),
            ],
          ),
        ),
        Expanded(
          child: storeName.isEmpty
              ? const EmptyState(
                  icon: Icons.storefront_outlined,
                  message: 'Choose a store to review quantities.',
                )
              : rows.when(
                  loading: () =>
                      const Center(child: CircularProgressIndicator()),
                  error: (error, _) => ErrorView(
                    message: _message(error, 'Could not load Qty Check.'),
                    onRetry: () =>
                        ref.invalidate(qtyCheckRowsProvider(storeName)),
                  ),
                  data: (items) => items.isEmpty
                      ? const EmptyState(
                          icon: Icons.task_alt_rounded,
                          message: 'Nothing is waiting for quantity review.',
                        )
                      : RefreshIndicator(
                          onRefresh: () async =>
                              ref.invalidate(qtyCheckRowsProvider(storeName)),
                          child: ListView.builder(
                            padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
                            itemCount: items.length,
                            itemBuilder: (_, index) => _QtyCard(
                              row: items[index],
                              busy: busy,
                              onReview: onReview,
                              onDetails: onDetails,
                            ),
                          ),
                        ),
                ),
        ),
      ],
    );
  }
}

class _QtyCard extends StatelessWidget {
  const _QtyCard({
    required this.row,
    required this.busy,
    required this.onReview,
    required this.onDetails,
  });

  final QtyCheckRow row;
  final bool busy;
  final ValueChanged<QtyCheckRow>? onReview;
  final ValueChanged<QtyCheckRow>? onDetails;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              row.productName,
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              'Code ${row.productCode}${row.unitDescription == null ? '' : ' · ${row.unitDescription}'}',
              style: const TextStyle(fontSize: 12, color: AppColors.textMuted),
            ),
            const SizedBox(height: 12),
            MetricRow(
              tiles: [
                MetricTile(
                  label: 'Suggested',
                  value: row.orderQty.toString(),
                  icon: Icons.shopping_cart_outlined,
                  color: AppColors.accent,
                ),
                MetricTile(
                  label: 'Stock',
                  value: _num(row.totalStock),
                  icon: Icons.inventory_2_outlined,
                  color: AppColors.info,
                ),
                MetricTile(
                  label: 'Sales qty',
                  value: _num(row.salesQty),
                  icon: Icons.trending_up_rounded,
                  color: AppColors.success,
                ),
                MetricTile(
                  label: 'MRP',
                  value: _num(row.mrp),
                  icon: Icons.currency_rupee_rounded,
                  color: AppColors.warning,
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: busy || onDetails == null
                        ? null
                        : () => onDetails!(row),
                    child: const Text('Evidence'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: FilledButton(
                    onPressed:
                        busy || onReview == null ? null : () => onReview!(row),
                    child: const Text('Review qty'),
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

class _QtyDetailsSheet extends ConsumerWidget {
  const _QtyDetailsSheet({required this.row, required this.request});

  final QtyCheckRow row;
  final QtyCheckRequest request;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final details = ref.watch(qtyCheckDetailsProvider(request));
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.9,
      minChildSize: 0.55,
      builder: (_, controller) => details.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => ErrorView(
          message: _message(error, 'Could not load product evidence.'),
          onRetry: () => ref.invalidate(qtyCheckDetailsProvider(request)),
        ),
        data: (value) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
          children: [
            Center(
              child: Container(
                width: 44,
                height: 4,
                decoration: BoxDecoration(
                  color: AppColors.ruleStrong,
                  borderRadius: BorderRadius.circular(99),
                ),
              ),
            ),
            const SizedBox(height: 18),
            Text(
              row.productName,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            Text(
              '${request.mode == 'local' ? 'Local OrderNMC copy' : 'Live branch'} · Code ${row.productCode}',
              style: const TextStyle(color: AppColors.textMuted),
            ),
            const SizedBox(height: 20),
            _EvidenceSection(
              title: 'Monthly statistics',
              empty: 'No recent monthly statistics.',
              children: [
                for (final item in value.monthly)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(item.month),
                    subtitle: Text(
                      'Sold ${_num(item.sales)} · Purchased ${_num(item.purchases)}',
                    ),
                    trailing: Text('Stock ${_num(item.stock)}'),
                  ),
              ],
            ),
            _EvidenceSection(
              title: 'Purchase / GRN history',
              empty: 'No purchase history.',
              children: [
                for (final item in value.purchases)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(item.supplierName ?? 'Unknown supplier'),
                    subtitle: Text(_dateTime(item.grnAt)),
                    trailing: Text('Received ${_num(item.receivedStock)}'),
                  ),
              ],
            ),
            _EvidenceSection(
              title: 'Sales history',
              empty: 'No sales history.',
              children: [
                for (final item in value.sales)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(item.customer ?? item.billNumber ?? 'Sale'),
                    subtitle: Text(
                      '${item.salesperson ?? 'Unknown salesperson'} · ${_dateTime(item.billAt)}',
                    ),
                    trailing: Text('Qty ${_num(item.quantity)}'),
                  ),
              ],
            ),
            _EvidenceSection(
              title: 'Previous orders',
              empty: 'No previous-order history.',
              children: [
                for (final item in value.history)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                        item.remarks ?? item.wantedType ?? 'Previous order'),
                    subtitle: Text(
                      '${item.supplier ?? 'No supplier'} · ${_dateTime(item.wantedAt)}',
                    ),
                    trailing: Text('Qty ${_num(item.orderQty)}'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _EvidenceSection extends StatelessWidget {
  const _EvidenceSection({
    required this.title,
    required this.empty,
    required this.children,
  });

  final String title;
  final String empty;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: ExpansionTile(
        title: Text(title),
        subtitle: Text(children.isEmpty ? empty : '${children.length} records'),
        childrenPadding: const EdgeInsets.symmetric(horizontal: 16),
        children: children,
      ),
    );
  }
}

class _OrderSettings {
  const _OrderSettings({
    required this.minDays,
    required this.maxDays,
    required this.mode,
  });

  final int minDays;
  final int maxDays;
  final String mode;
}

class _OrderSettingsSheet extends StatefulWidget {
  const _OrderSettingsSheet({required this.defaults});

  final LegacyDefaults defaults;

  @override
  State<_OrderSettingsSheet> createState() => _OrderSettingsSheetState();
}

class _OrderSettingsSheetState extends State<_OrderSettingsSheet> {
  late final TextEditingController _min;
  late final TextEditingController _max;
  String _mode = 'local';

  @override
  void initState() {
    super.initState();
    _min = TextEditingController(text: widget.defaults.minDays.toString());
    _max = TextEditingController(text: widget.defaults.maxDays.toString());
  }

  @override
  void dispose() {
    _min.dispose();
    _max.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.viewInsetsOf(context).bottom,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Order process', style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 8),
          const Text(
            'The server runs a full sync first, then generates the order. It can take several minutes.',
            style: TextStyle(color: AppColors.textMuted),
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _min,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Min days'),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: TextField(
                  controller: _max,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Max days'),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'local', label: Text('Local copy')),
              ButtonSegment(value: 'remote', label: Text('Live branch')),
            ],
            selected: {_mode},
            onSelectionChanged: (value) => setState(() => _mode = value.first),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _submit,
            child: const Text('Start order process'),
          ),
        ],
      ),
    );
  }

  void _submit() {
    final min = int.tryParse(_min.text.trim());
    final max = int.tryParse(_max.text.trim());
    if (min == null || max == null || min <= 0 || max <= 0 || min > max) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid day range.')),
      );
      return;
    }
    Navigator.of(context).pop(_OrderSettings(
      minDays: min,
      maxDays: max,
      mode: _mode,
    ));
  }
}

String _message(Object error, String fallback) =>
    error is ApiException ? error.message : fallback;

String _num(num? value) {
  if (value == null) return '—';
  return value == value.roundToDouble()
      ? value.toInt().toString()
      : value.toStringAsFixed(2);
}

String _dateTime(DateTime? value) {
  if (value == null) return '—';
  String two(int part) => part.toString().padLeft(2, '0');
  return '${two(value.day)}/${two(value.month)}/${value.year} '
      '${two(value.hour)}:${two(value.minute)}';
}
