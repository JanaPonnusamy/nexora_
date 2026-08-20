import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/error_view.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/core/widgets/offline_banner.dart';
import 'package:nexora_mobile/features/procurement/application/cycle_providers.dart';
import 'package:nexora_mobile/features/procurement/application/stock_distribution_providers.dart';
import 'package:nexora_mobile/features/procurement/domain/stock_distribution_models.dart';

class StockDistributionScreen extends ConsumerStatefulWidget {
  const StockDistributionScreen({super.key});

  @override
  ConsumerState<StockDistributionScreen> createState() =>
      _StockDistributionScreenState();
}

class _StockDistributionScreenState
    extends ConsumerState<StockDistributionScreen> {
  final _selected = <String>{};
  String? _busyAction;
  String? _expandedRunId;
  Future<DistributionRunDetail>? _detail;

  @override
  Widget build(BuildContext context) {
    final dashboard = ref.watch(stockDistributionDashboardProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Stock Distribution'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            onPressed: () => ref.invalidate(stockDistributionDashboardProvider),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: Column(
        children: [
          const OfflineBanner(
            message: 'Offline — distribution controls need a connection.',
          ),
          Expanded(
            child: dashboard.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => ErrorView(
                message: error is ApiException
                    ? error.message
                    : 'Could not load stock distribution.',
                onRetry: () =>
                    ref.invalidate(stockDistributionDashboardProvider),
              ),
              data: _content,
            ),
          ),
        ],
      ),
    );
  }

  Widget _content(StockDistributionDashboard dashboard) {
    return RefreshIndicator(
      onRefresh: () async {
        ref.invalidate(stockDistributionDashboardProvider);
        await ref.read(stockDistributionDashboardProvider.future);
      },
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
        children: [
          SectionHeader(
            title: 'TARGET STORES',
            icon: Icons.storefront_outlined,
            trailing: InfoChip(
              label: '${_selected.length} selected',
              color: AppColors.accentInk,
            ),
          ),
          if (dashboard.targets.isEmpty)
            const EmptyState(
              icon: Icons.store_mall_directory_outlined,
              message: 'No target stores are configured.',
            )
          else
            for (final target in dashboard.targets)
              _TargetTile(
                target: target,
                selected: _selected.contains(target.storeId),
                onChanged: target.enabled
                    ? (selected) => setState(() {
                          if (selected) {
                            _selected.add(target.storeId);
                          } else {
                            _selected.remove(target.storeId);
                          }
                        })
                    : null,
              ),
          const SizedBox(height: 12),
          FilledButton.icon(
            onPressed: _busyAction == null
                ? () => _generate(dashboard, selectedOnly: false)
                : null,
            icon: const Icon(Icons.play_arrow_rounded),
            label: Text(_busyAction == 'all' ? 'Generating…' : 'Generate all'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _busyAction == null && _selected.isNotEmpty
                ? () => _generate(dashboard, selectedOnly: true)
                : null,
            icon: const Icon(Icons.checklist_rounded),
            label: Text(
              _busyAction == 'selected'
                  ? 'Generating…'
                  : 'Generate selected (${_selected.length})',
            ),
          ),
          const SizedBox(height: 22),
          const SectionHeader(
            title: 'RUN HISTORY',
            icon: Icons.history_rounded,
          ),
          if (dashboard.runs.isEmpty)
            const EmptyState(
              icon: Icons.hourglass_empty_rounded,
              message: 'No distribution runs yet.',
            )
          else
            for (final run in dashboard.runs)
              _RunCard(
                run: run,
                expanded: _expandedRunId == run.runId,
                retrying: _busyAction == 'retry:${run.runId}',
                onToggle: () => _toggleDetail(run.runId),
                onRetry: run.storesFailed > 0 ? () => _retry(run.runId) : null,
                detail: _expandedRunId == run.runId ? _detail : null,
              ),
        ],
      ),
    );
  }

  Future<void> _generate(
    StockDistributionDashboard dashboard, {
    required bool selectedOnly,
  }) async {
    final scope = ref.read(cycleScopeProvider);
    final actor = ref.read(cycleActorProvider);
    if (scope == null || actor == null || actor.isEmpty) return;
    final confirmed = await _confirm(
      'Generate stock distribution?',
      selectedOnly
          ? 'This will update supplier stock and generate exports for '
              '${_selected.length} selected store${_selected.length == 1 ? '' : 's'}.'
          : 'This will update supplier stock and generate exports for every '
              'enabled target store. It can take several minutes.',
    );
    if (!confirmed) return;
    setState(() => _busyAction = selectedOnly ? 'selected' : 'all');
    try {
      final result = await ref.read(stockDistributionApiProvider).generate(
            tenantId: scope.tenantId,
            sourceStoreCode: dashboard.sourceStoreCode,
            actor: actor,
            storeIds: selectedOnly ? _selected.toList(growable: false) : null,
          );
      if (result.error != null) {
        throw ApiException(message: result.error!);
      }
      _say('${result.succeeded} succeeded, ${result.failed} failed.');
      ref.invalidate(stockDistributionDashboardProvider);
    } on ApiException catch (error) {
      _say(error.message);
    } finally {
      if (mounted) setState(() => _busyAction = null);
    }
  }

  Future<void> _retry(String runId) async {
    final actor = ref.read(cycleActorProvider);
    if (actor == null || actor.isEmpty) return;
    setState(() => _busyAction = 'retry:$runId');
    try {
      final result = await ref
          .read(stockDistributionApiProvider)
          .retry(runId: runId, actor: actor);
      _say('${result.succeeded} succeeded, ${result.failed} still failed.');
      ref.invalidate(stockDistributionDashboardProvider);
    } on ApiException catch (error) {
      _say(error.message);
    } finally {
      if (mounted) setState(() => _busyAction = null);
    }
  }

  void _toggleDetail(String runId) {
    setState(() {
      if (_expandedRunId == runId) {
        _expandedRunId = null;
        _detail = null;
      } else {
        _expandedRunId = runId;
        _detail = ref.read(stockDistributionApiProvider).detail(runId);
      }
    });
  }

  Future<bool> _confirm(String title, String message) async =>
      await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(title),
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: const Text('Generate'),
            ),
          ],
        ),
      ) ??
      false;

  void _say(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}

class _TargetTile extends StatelessWidget {
  const _TargetTile({
    required this.target,
    required this.selected,
    required this.onChanged,
  });

  final DistributionTarget target;
  final bool selected;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    return CheckboxListTile(
      value: selected,
      onChanged:
          onChanged == null ? null : (value) => onChanged!(value ?? false),
      controlAffinity: ListTileControlAffinity.leading,
      contentPadding: EdgeInsets.zero,
      title: Text('${target.storeName} (${target.storeCode})'),
      subtitle: Text(
        target.localSupplierCode == null
            ? 'Supplier mapping missing'
            : 'Supplier ${target.localSupplierCode} · '
                '${target.whatsappGroup ?? target.phoneNumber ?? 'WhatsApp not configured'}',
      ),
      secondary: StatusBadge(
        label: target.enabled
            ? target.ready
                ? 'Ready'
                : 'Needs setup'
            : 'Disabled',
        color: target.ready
            ? AppColors.success
            : target.enabled
                ? AppColors.warning
                : AppColors.textMuted,
        dense: true,
      ),
    );
  }
}

class _RunCard extends StatelessWidget {
  const _RunCard({
    required this.run,
    required this.expanded,
    required this.retrying,
    required this.onToggle,
    required this.onRetry,
    required this.detail,
  });

  final DistributionRun run;
  final bool expanded;
  final bool retrying;
  final VoidCallback onToggle;
  final VoidCallback? onRetry;
  final Future<DistributionRunDetail>? detail;

  @override
  Widget build(BuildContext context) {
    final success = run.status == 'completed' && run.storesFailed == 0;
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
                    '${run.sourceStoreCode} distribution',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                StatusBadge(
                  label: run.status,
                  color: success
                      ? AppColors.success
                      : run.storesFailed > 0
                          ? AppColors.danger
                          : AppColors.warning,
                  dense: true,
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              '${run.storesSucceeded}/${run.storesTotal} stores · '
              '${run.totalProducts} products · ${run.totalStockQty.compact} units',
              style:
                  const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
            ),
            if (run.error != null)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Text(run.error!,
                    style: const TextStyle(color: AppColors.dangerInk)),
              ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                OutlinedButton(
                  onPressed: onToggle,
                  child: Text(expanded ? 'Hide details' : 'View details'),
                ),
                if (onRetry != null)
                  OutlinedButton(
                    onPressed: retrying ? null : onRetry,
                    child: Text(retrying ? 'Retrying…' : 'Retry failed'),
                  ),
              ],
            ),
            if (expanded && detail != null) ...[
              const Divider(height: 22),
              FutureBuilder<DistributionRunDetail>(
                future: detail,
                builder: (_, snapshot) {
                  if (snapshot.connectionState != ConnectionState.done) {
                    return const LinearProgressIndicator();
                  }
                  if (snapshot.hasError) {
                    return const Text('Could not load details.');
                  }
                  return Column(
                    children: [
                      for (final item in snapshot.data?.items ?? const [])
                        _RunItemRow(item: item),
                    ],
                  );
                },
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RunItemRow extends StatelessWidget {
  const _RunItemRow({required this.item});

  final DistributionRunItem item;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 5),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.storeCode,
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                Text(
                  'Stock ${item.stockStatus} · Excel ${item.excelStatus} · '
                  'WhatsApp ${item.whatsappStatus}',
                  style: const TextStyle(
                      fontSize: 11.5, color: AppColors.textMuted),
                ),
                if (item.error != null)
                  Text(item.error!,
                      style: const TextStyle(
                          fontSize: 11.5, color: AppColors.dangerInk)),
              ],
            ),
          ),
          Text('${item.rowsExported} rows'),
        ],
      ),
    );
  }
}

extension on double {
  String get compact =>
      this == roundToDouble() ? toInt().toString() : toString();
}
