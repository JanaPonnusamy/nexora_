import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/error_view.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/core/widgets/offline_banner.dart';
import 'package:nexora_mobile/features/procurement/application/cycle_providers.dart';
import 'package:nexora_mobile/features/procurement/application/refresh_compare_providers.dart';
import 'package:nexora_mobile/features/procurement/domain/refresh_compare_models.dart';

class RefreshCompareScreen extends ConsumerStatefulWidget {
  const RefreshCompareScreen({super.key});

  @override
  ConsumerState<RefreshCompareScreen> createState() =>
      _RefreshCompareScreenState();
}

class _RefreshCompareScreenState extends ConsumerState<RefreshCompareScreen> {
  String? _cycleId;
  String? _sourceId;
  String? _targetId;
  List<RefreshCompareRow>? _rows;
  bool _busy = false;
  bool _changedOnly = true;
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final setup = ref.watch(refreshCompareSetupProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Refresh Compare')),
      body: Column(
        children: [
          const OfflineBanner(
            message: 'Offline — comparing refreshes needs a connection.',
          ),
          Expanded(
            child: setup.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => ErrorView(
                message: error is ApiException
                    ? error.message
                    : 'Could not load refresh history.',
                onRetry: () => ref.invalidate(refreshCompareSetupProvider),
              ),
              data: _content,
            ),
          ),
        ],
      ),
    );
  }

  Widget _content(RefreshCompareSetup setup) {
    if (setup.refreshes.length < 2) {
      return const Center(
        child: EmptyState(
          icon: Icons.compare_arrows_rounded,
          message: 'At least two refreshes are needed for comparison.',
        ),
      );
    }
    final cycleIds = setup.refreshes.map((refresh) => refresh.cycleId).toSet();
    final defaultCycle = setup.cycles
        .where((cycle) => cycleIds.contains(cycle.cycleId))
        .firstOrNull
        ?.cycleId;
    final cycleId = cycleIds.contains(_cycleId)
        ? _cycleId!
        : defaultCycle ?? cycleIds.first;
    final refreshes = setup.refreshes
        .where((refresh) => refresh.cycleId == cycleId)
        .toList()
      ..sort((a, b) => b.number.compareTo(a.number));
    final targetId = refreshes.any((refresh) => refresh.refreshId == _targetId)
        ? _targetId!
        : refreshes.first.refreshId;
    final sourceId = refreshes.any((refresh) => refresh.refreshId == _sourceId)
        ? _sourceId!
        : refreshes.length > 1
            ? refreshes[1].refreshId
            : refreshes.first.refreshId;
    final cycleName = <String, String>{
      for (final cycle in setup.cycles) cycle.cycleId: cycle.name,
    };

    final visible = (_rows ?? const <RefreshCompareRow>[]).where((row) {
      if (_changedOnly && row.change == RefreshChangeType.unchanged) {
        return false;
      }
      final query = _query.toLowerCase();
      return query.isEmpty ||
          '${row.productName} ${row.productCode}'.toLowerCase().contains(query);
    }).toList(growable: false);

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        DropdownButtonFormField<String>(
          initialValue: cycleId,
          decoration: const InputDecoration(labelText: 'Cycle'),
          items: cycleIds
              .map((id) => DropdownMenuItem(
                    value: id,
                    child: Text(cycleName[id] ?? 'Cycle ${id.take(8)}'),
                  ))
              .toList(growable: false),
          onChanged: (value) => setState(() {
            _cycleId = value;
            _sourceId = null;
            _targetId = null;
            _rows = null;
          }),
        ),
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          initialValue: sourceId,
          decoration: const InputDecoration(labelText: 'From'),
          items: _refreshItems(refreshes),
          onChanged: (value) => setState(() {
            _sourceId = value;
            _rows = null;
          }),
        ),
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          initialValue: targetId,
          decoration: const InputDecoration(labelText: 'To'),
          items: _refreshItems(refreshes),
          onChanged: (value) => setState(() {
            _targetId = value;
            _rows = null;
          }),
        ),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: _busy || sourceId == targetId
              ? null
              : () => _compare(sourceId, targetId),
          icon: _busy
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.compare_arrows_rounded),
          label: Text(_busy ? 'Comparing…' : 'Compare final orders'),
        ),
        if (_rows != null) ...[
          const SizedBox(height: 18),
          Row(
            children: [
              Expanded(
                child: TextField(
                  decoration: const InputDecoration(
                    hintText: 'Filter products',
                    prefixIcon: Icon(Icons.search_rounded),
                  ),
                  onChanged: (value) => setState(() => _query = value.trim()),
                ),
              ),
              const SizedBox(width: 8),
              FilterChip(
                label: const Text('Changed'),
                selected: _changedOnly,
                onSelected: (value) => setState(() => _changedOnly = value),
              ),
            ],
          ),
          const SizedBox(height: 12),
          MetricRow(
            tiles: [
              MetricTile(
                label: 'Changed',
                value: _rows!
                    .where((row) => row.change != RefreshChangeType.unchanged)
                    .length
                    .toString(),
                icon: Icons.change_circle_outlined,
                color: AppColors.warning,
              ),
              MetricTile(
                label: 'Added',
                value: _count(RefreshChangeType.added).toString(),
                icon: Icons.add_circle_outline,
                color: AppColors.success,
              ),
              MetricTile(
                label: 'Removed',
                value: _count(RefreshChangeType.removed).toString(),
                icon: Icons.remove_circle_outline,
                color: AppColors.danger,
              ),
            ],
          ),
          const SizedBox(height: 12),
          if (visible.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 32),
              child: EmptyState(
                icon: Icons.done_all_rounded,
                message: 'No products match these comparison filters.',
              ),
            )
          else
            for (final row in visible) _CompareCard(row: row),
        ],
      ],
    );
  }

  List<DropdownMenuItem<String>> _refreshItems(
    List<ProcurementRefresh> refreshes,
  ) =>
      refreshes
          .map((refresh) => DropdownMenuItem(
                value: refresh.refreshId,
                child: Text('${refresh.label} · ${refresh.status}'),
              ))
          .toList(growable: false);

  Future<void> _compare(String sourceId, String targetId) async {
    final scope = ref.read(cycleScopeProvider);
    if (scope == null) return;
    setState(() => _busy = true);
    try {
      final rows = await ref.read(refreshCompareApiProvider).compare(
            tenantId: scope.tenantId,
            sourceRefreshId: sourceId,
            targetRefreshId: targetId,
          );
      if (mounted) setState(() => _rows = rows);
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  int _count(RefreshChangeType type) =>
      _rows!.where((row) => row.change == type).length;
}

class _CompareCard extends StatelessWidget {
  const _CompareCard({required this.row});

  final RefreshCompareRow row;

  @override
  Widget build(BuildContext context) {
    final color = switch (row.change) {
      RefreshChangeType.added => AppColors.success,
      RefreshChangeType.removed => AppColors.danger,
      RefreshChangeType.increased => AppColors.info,
      RefreshChangeType.decreased => AppColors.warning,
      RefreshChangeType.unchanged => AppColors.textMuted,
    };
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
                  child: Text(row.productName,
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                ),
                StatusBadge(label: row.change.label, color: color, dense: true),
              ],
            ),
            const SizedBox(height: 3),
            Text(row.productCode,
                style:
                    const TextStyle(fontSize: 12, color: AppColors.textMuted)),
            const SizedBox(height: 10),
            Text(
              '${row.sourceQty.compact}  →  ${row.targetQty.compact}   '
              '(${row.difference.signed})',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            if (row.sourceSkipped || row.targetSkipped)
              const Padding(
                padding: EdgeInsets.only(top: 6),
                child: Text('Skipped in one or both refreshes',
                    style:
                        TextStyle(fontSize: 12, color: AppColors.warningInk)),
              ),
          ],
        ),
      ),
    );
  }
}

extension on String {
  String take(int length) => substring(0, this.length.clamp(0, length));
}

extension on double {
  String get compact =>
      this == roundToDouble() ? toInt().toString() : toString();
  String get signed => this > 0 ? '+$compact' : compact;
}
