import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/error_view.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/core/widgets/offline_banner.dart';
import 'package:nexora_mobile/features/procurement/application/cycle_providers.dart';
import 'package:nexora_mobile/features/procurement/domain/cycle_models.dart';

/// Run and monitor a procurement cycle from a phone.
///
/// Scoped deliberately: the desktop console also edits order items line by
/// line, which does not survive phone width and is not what someone away from
/// a desk needs. What they need is to see where the cycle is, start the next
/// refresh, and close one — the three actions that block other people.
class CycleConsoleScreen extends ConsumerStatefulWidget {
  const CycleConsoleScreen({super.key});

  @override
  ConsumerState<CycleConsoleScreen> createState() => _CycleConsoleScreenState();
}

class _CycleConsoleScreenState extends ConsumerState<CycleConsoleScreen> {
  final _log = AppLogger.of('CycleConsole');

  /// Null means every status. The server filters, so this is not a local
  /// filter over a partial page.
  String? _status;
  bool _busy = false;

  @override
  Widget build(BuildContext context) {
    final scope = ref.watch(cycleScopeProvider);
    final cycles = ref.watch(cyclesProvider(_status));

    return Scaffold(
      appBar: AppBar(title: const Text('Cycle Console')),
      body: Column(
        children: [
          const OfflineBanner(
            message: 'Offline — cycle status needs a connection.',
          ),
          _StatusFilter(
            selected: _status,
            onChanged: (value) => setState(() => _status = value),
          ),
          Expanded(
            child: scope == null
                ? const Center(
                    child: EmptyState(
                      icon: Icons.storefront_outlined,
                      message: 'Choose a store to see its cycles.',
                    ),
                  )
                : cycles.when(
                    loading: () =>
                        const Center(child: CircularProgressIndicator()),
                    error: (e, _) => ErrorView(
                      message: e is ApiException
                          ? e.message
                          : 'Could not load cycles.',
                      onRetry: () => ref.invalidate(cyclesProvider(_status)),
                    ),
                    data: (page) => page.items.isEmpty
                        ? const Center(
                            child: EmptyState(
                              icon: Icons.event_repeat_outlined,
                              message: 'No cycles for this store yet.',
                            ),
                          )
                        : RefreshIndicator(
                            onRefresh: () async =>
                                ref.invalidate(cyclesProvider(_status)),
                            child: ListView.builder(
                              padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                              itemCount: page.items.length,
                              itemBuilder: (_, i) => _CycleCard(
                                cycle: page.items[i],
                                busy: _busy,
                                onCloseCycle: _closeCycle,
                                onStartRefresh: _startRefresh,
                                onCloseRefresh: _closeRefresh,
                              ),
                            ),
                          ),
                  ),
          ),
        ],
      ),
    );
  }

  ({CycleScope scope, String actor})? _requireScope() {
    final scope = ref.read(cycleScopeProvider);
    final actor = ref.read(cycleActorProvider);
    if (scope == null || actor == null || actor.isEmpty) {
      _say('Sign in and choose a store first.');
      return null;
    }
    return (scope: scope, actor: actor);
  }

  void _say(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  Future<T?> _guard<T>(Future<T> Function() action) async {
    setState(() => _busy = true);
    try {
      return await action();
    } on ApiException catch (e) {
      _log.warning('Cycle action failed: ${e.message}');
      _say(
        e.isNetwork
            ? 'Cannot reach the server. Nothing was changed.'
            : e.message,
      );
      return null;
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _startRefresh(ProcurementCycle cycle) async {
    final ctx = _requireScope();
    if (ctx == null) return;

    final confirmed = await _confirm(
      title: 'Start the next refresh?',
      // Named as slow because it is: the server runs the engine and generates
      // working items before responding, and a user who thinks the app has
      // frozen will kill it mid-run.
      body: 'This runs the procurement engine for "${cycle.name}" and can take '
          'a minute or two. Keep the app open until it finishes.',
      confirmLabel: 'Start refresh',
    );
    if (!confirmed) return;

    final result = await _guard(
      () => ref.read(cycleApiProvider).createRefresh(
        tenantId: ctx.scope.tenantId,
        cycleId: cycle.cycleId,
        payload: {'created_by': ctx.actor},
      ),
    );
    if (result == null) return;

    ref.invalidate(cyclesProvider(_status));
    _say('Refresh started.');
  }

  Future<void> _closeRefresh(ProcurementCycle cycle) async {
    final ctx = _requireScope();
    final refreshId = cycle.activeRefreshId;
    if (ctx == null || refreshId == null) return;

    final confirmed = await _confirm(
      title: 'Close this refresh?',
      body: 'The refresh becomes read-only. The cycle stays open, so a new '
          'refresh can be started after it.',
      confirmLabel: 'Close refresh',
    );
    if (!confirmed) return;

    final outcome = await _guard(
      () => ref.read(cycleApiProvider).closeRefresh(
            tenantId: ctx.scope.tenantId,
            refreshId: refreshId,
            closedBy: ctx.actor,
          ),
    );
    if (outcome == null) return;

    ref.invalidate(cyclesProvider(_status));
    _say('Refresh closed.');
  }

  Future<void> _closeCycle(ProcurementCycle cycle) async {
    final ctx = _requireScope();
    if (ctx == null) return;

    final confirmed = await _confirm(
      title: 'Close "${cycle.name}"?',
      body: 'This reconciles against synced purchases, stamps the closing GRN '
          'and sale-bill numbers, and opens a fresh cycle.',
      confirmLabel: 'Close cycle',
    );
    if (!confirmed) return;

    var outcome = await _guard(
      () => ref.read(cycleApiProvider).closeCycle(
            tenantId: ctx.scope.tenantId,
            cycleId: cycle.cycleId,
            closedBy: ctx.actor,
          ),
    );
    if (outcome == null) return;

    // `pending_confirm` is the server asking a question, not refusing. Forcing
    // on the user's behalf would close over unresolved items nobody agreed to
    // abandon — so it is put back to them, naming the count.
    if (outcome.needsConfirmation) {
      final count = outcome.pendingCount;
      final forced = await _confirm(
        title: 'Unresolved items remain',
        body: count == null
            ? 'Some items on this cycle are still unresolved. Closing now '
                'leaves them behind.'
            : '$count item${count == 1 ? '' : 's'} on this cycle '
                '${count == 1 ? 'is' : 'are'} still unresolved. Closing now '
                'leaves ${count == 1 ? 'it' : 'them'} behind.',
        confirmLabel: 'Close anyway',
        destructive: true,
      );
      if (!forced) return;

      outcome = await _guard(
        () => ref.read(cycleApiProvider).closeCycle(
              tenantId: ctx.scope.tenantId,
              cycleId: cycle.cycleId,
              closedBy: ctx.actor,
              force: true,
            ),
      );
      if (outcome == null) return;
    }

    ref.invalidate(cyclesProvider(_status));
    _say('Cycle closed. A new one has been opened.');
  }

  Future<bool> _confirm({
    required String title,
    required String body,
    required String confirmLabel,
    bool destructive = false,
  }) async {
    final answer = await showDialog<bool>(
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
            style: destructive
                ? TextButton.styleFrom(foregroundColor: AppColors.dangerInk)
                : null,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: Text(confirmLabel),
          ),
        ],
      ),
    );
    return answer ?? false;
  }
}

class _StatusFilter extends StatelessWidget {
  const _StatusFilter({required this.selected, required this.onChanged});

  final String? selected;
  final ValueChanged<String?> onChanged;

  static const _options = <(String?, String)>[
    (null, 'All'),
    ('ACTIVE', 'Open'),
    ('CLOSED', 'Closed'),
  ];

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 52,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        children: [
          for (final (value, label) in _options)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                label: Text(label),
                selected: selected == value,
                onSelected: (_) => onChanged(value),
              ),
            ),
        ],
      ),
    );
  }
}

class _CycleCard extends StatelessWidget {
  const _CycleCard({
    required this.cycle,
    required this.busy,
    required this.onCloseCycle,
    required this.onStartRefresh,
    required this.onCloseRefresh,
  });

  final ProcurementCycle cycle;
  final bool busy;
  final ValueChanged<ProcurementCycle> onCloseCycle;
  final ValueChanged<ProcurementCycle> onStartRefresh;
  final ValueChanged<ProcurementCycle> onCloseRefresh;

  @override
  Widget build(BuildContext context) {
    final open = cycle.status.isOpen;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    cycle.name,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                StatusBadge(
                  // The server's own word when this build does not know the
                  // status — an unrecognised state is information, and
                  // relabelling it "Unknown" throws that away.
                  label: switch (cycle.status) {
                    CycleStatus.active => 'Open',
                    CycleStatus.closed => 'Closed',
                    CycleStatus.draft => 'Draft',
                    CycleStatus.unknown =>
                      cycle.rawStatus.isEmpty ? '—' : cycle.rawStatus,
                  },
                  color: open ? AppColors.success : AppColors.textMuted,
                  dense: true,
                ),
              ],
            ),
            const SizedBox(height: 12),
            _Counters(cycle: cycle),
            if (open) ...[
              const SizedBox(height: 14),
              Wrap(
                spacing: 10,
                runSpacing: 8,
                children: [
                  // §3.8: a themed button cannot be a direct child of a Wrap
                  // either — both measure inflexible children with an unbounded
                  // main axis, and the theme's Size.fromHeight is infinite-width.
                  if (cycle.hasActiveRefresh)
                    OutlinedButton(
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size(0, 40),
                      ),
                      onPressed: busy ? null : () => onCloseRefresh(cycle),
                      child: const Text('Close refresh'),
                    )
                  else
                    FilledButton(
                      style: FilledButton.styleFrom(
                        minimumSize: const Size(0, 40),
                      ),
                      onPressed: busy ? null : () => onStartRefresh(cycle),
                      child: const Text('Start refresh'),
                    ),
                  TextButton(
                    style: TextButton.styleFrom(
                      minimumSize: const Size(0, 40),
                      foregroundColor: AppColors.dangerInk,
                    ),
                    onPressed: busy ? null : () => onCloseCycle(cycle),
                    child: const Text('Close cycle'),
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

class _Counters extends StatelessWidget {
  const _Counters({required this.cycle});

  final ProcurementCycle cycle;

  @override
  Widget build(BuildContext context) {
    // Not MetricTile: it is a fixed 92px, and a GRN number does not fit. A
    // truncated counter reading is worse than none.
    return Column(
      children: [
        Row(
          children: [
            Expanded(
              child: _Counter(label: 'Start GRN', value: cycle.startGrnNumber),
            ),
            Expanded(
              child: _Counter(
                label: 'Start bill',
                value: cycle.startSaleBillNumber,
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _Counter(label: 'End GRN', value: cycle.endGrnNumber),
            ),
            Expanded(
              child: _Counter(
                label: 'End bill',
                value: cycle.endSaleBillNumber,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _Counter extends StatelessWidget {
  const _Counter({required this.label, required this.value});

  final String label;
  final String? value;

  @override
  Widget build(BuildContext context) {
    final stamped = value != null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 11.5, color: AppColors.textMuted),
        ),
        const SizedBox(height: 2),
        Text(
          // "Not stamped" rather than a dash or a zero: these are counter
          // readings, and a 0 would read as a real one.
          stamped ? value! : 'Not stamped',
          style: TextStyle(
            fontSize: 14,
            fontWeight: stamped ? FontWeight.w600 : FontWeight.w400,
            color: stamped ? AppColors.text : AppColors.textMuted,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ],
    );
  }
}
