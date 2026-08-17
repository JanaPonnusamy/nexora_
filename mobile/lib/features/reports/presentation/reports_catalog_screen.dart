import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/reports/application/reports_providers.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';
import 'package:nexora_mobile/features/reports/presentation/report_runner_screen.dart';

/// The report catalog, driven entirely by `GET /api/reports`.
///
/// Nothing about any individual report is hard-coded here: a report added on
/// the server shows up on the next launch, with the right filter controls,
/// without an app release. That is the whole reason this module is small.
class ReportsCatalogScreen extends ConsumerWidget {
  const ReportsCatalogScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final grouped = ref.watch(groupedReportCatalogProvider);
    final scope = ref.watch(reportScopeProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Reports')),
      body: RefreshIndicator(
        onRefresh: () async {
          ref.invalidate(reportCatalogProvider);
          await ref.read(reportCatalogProvider.future);
        },
        child: scope == null
            ? const _Scrollable(
                child: EmptyState(
                  message: 'Reports are scoped to a store.\nPick a store to '
                      'run them.',
                  icon: Icons.store_outlined,
                ),
              )
            : grouped.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => _Scrollable(
                  child: EmptyState(
                    message: 'Could not load the report catalog.\n$e',
                    icon: Icons.error_outline_rounded,
                  ),
                ),
                data: (groups) => groups.isEmpty
                    ? const _Scrollable(
                        child: EmptyState(
                          message: 'No reports are published for this server.',
                          icon: Icons.insert_chart_outlined,
                        ),
                      )
                    : ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.fromLTRB(16, 12, 16, 28),
                        children: [
                          for (final entry in groups.entries) ...[
                            SectionHeader(
                              title: entry.key.toUpperCase(),
                              icon: _groupIcon(entry.key),
                            ),
                            StatusCard(
                              accentColor: AppColors.rule,
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                                vertical: 2,
                              ),
                              child: Column(
                                children: [
                                  for (final (i, def)
                                      in entry.value.indexed) ...[
                                    if (i > 0) const Divider(height: 1),
                                    _ReportTile(def: def),
                                  ],
                                ],
                              ),
                            ),
                            const SizedBox(height: 16),
                          ],
                        ],
                      ),
              ),
      ),
    );
  }

  static IconData _groupIcon(String group) => switch (group.toLowerCase()) {
        'sales' => Icons.point_of_sale_outlined,
        'margin' => Icons.trending_up_rounded,
        'stock' => Icons.inventory_2_outlined,
        _ => Icons.insert_chart_outlined,
      };
}

class _ReportTile extends StatelessWidget {
  const _ReportTile({required this.def});

  final ReportDef def;

  @override
  Widget build(BuildContext context) {
    return ActionTile(
      title: def.label,
      subtitle: _inputs(),
      icon: Icons.summarize_outlined,
      color: AppColors.accent,
      onTap: () => Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => ReportRunnerScreen(def: def),
        ),
      ),
    );
  }

  /// Tells the user what the report will ask for *before* they tap into it.
  String _inputs() {
    final needs = <String>[
      if (def.needsDateRange) 'date range',
      if (def.needsDwellDays) 'idle days',
      if (def.needsDivision) 'division',
      if (def.needsSupplier) 'supplier (optional)',
    ];
    return needs.isEmpty ? 'Runs straight away' : 'Needs ${needs.join(', ')}';
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
