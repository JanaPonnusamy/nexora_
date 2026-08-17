import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/reports/application/reports_providers.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';

/// Filter sheet generated from a catalog entry.
///
/// Only the controls the report declares are shown — a stock report never
/// offers a date range, and a sales report never offers idle days. That is the
/// payoff of the server telling us what each report needs.
class ReportFilterSheet extends ConsumerStatefulWidget {
  const ReportFilterSheet({
    super.key,
    required this.def,
    required this.filters,
  });

  final ReportDef def;
  final ReportFilters filters;

  @override
  ConsumerState<ReportFilterSheet> createState() => _ReportFilterSheetState();
}

class _ReportFilterSheetState extends ConsumerState<ReportFilterSheet> {
  late ReportFilters _draft = widget.filters;
  late final TextEditingController _division = TextEditingController(
    text: widget.filters.divisionCode ?? '',
  );

  @override
  void dispose() {
    _division.dispose();
    super.dispose();
  }

  Future<void> _pickRange() async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      // Two years back covers every reporting window these reports support
      // without offering a range the store data cannot answer.
      firstDate: DateTime(now.year - 2),
      lastDate: now,
      initialDateRange: (_draft.from != null && _draft.to != null)
          ? DateTimeRange(start: _draft.from!, end: _draft.to!)
          : null,
    );
    if (picked == null || !mounted) return;
    setState(
        () => _draft = _draft.copyWith(from: picked.start, to: picked.end));
  }

  Future<void> _pickSupplier() async {
    final chosen = await showModalBottomSheet<SupplierOption?>(
      context: context,
      backgroundColor: AppColors.surfaceRaised,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const _SupplierPicker(),
    );
    if (!mounted) return;
    setState(() {
      _draft = chosen == null
          ? _draft.copyWith(clearSupplier: true)
          : _draft.copyWith(
              supplierCode: chosen.code,
              supplierName: chosen.label,
            );
    });
  }

  @override
  Widget build(BuildContext context) {
    final def = widget.def;

    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            def.label,
            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 16),
          if (def.needsDateRange) ...[
            const SectionHeader(
              title: 'DATE RANGE',
              icon: Icons.date_range_outlined,
            ),
            OutlinedButton.icon(
              onPressed: _pickRange,
              icon: const Icon(Icons.edit_calendar_outlined, size: 18),
              label: Text(
                (_draft.from != null && _draft.to != null)
                    ? '${_d(_draft.from!)} → ${_d(_draft.to!)}'
                    : 'Choose dates',
              ),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(46),
              ),
            ),
            const SizedBox(height: 16),
          ],
          if (def.needsDwellDays) ...[
            const SectionHeader(
              title: 'IDLE FOR AT LEAST',
              icon: Icons.hourglass_empty_rounded,
            ),
            Wrap(
              spacing: 8,
              children: [
                // The presets are the windows the legacy reports offered;
                // a free-text field here invites typos with no benefit.
                for (final days in [30, 60, 90, 120, 180, 365])
                  ChoiceChip(
                    label: Text('$days d'),
                    selected: _draft.dwellDays == days,
                    onSelected: (_) => setState(
                        () => _draft = _draft.copyWith(dwellDays: days)),
                  ),
              ],
            ),
            const SizedBox(height: 16),
          ],
          if (def.needsSupplier) ...[
            const SectionHeader(
              title: 'SUPPLIER (OPTIONAL)',
              icon: Icons.local_shipping_outlined,
            ),
            OutlinedButton.icon(
              onPressed: _pickSupplier,
              icon: const Icon(Icons.search_rounded, size: 18),
              label: Text(_draft.supplierName ?? 'All suppliers'),
              style: OutlinedButton.styleFrom(
                minimumSize: const Size.fromHeight(46),
              ),
            ),
            const SizedBox(height: 16),
          ],
          if (def.needsDivision) ...[
            const SectionHeader(
              title: 'DIVISION',
              icon: Icons.category_outlined,
            ),
            TextField(
              controller: _division,
              decoration: const InputDecoration(
                hintText: 'Division code',
              ),
              textCapitalization: TextCapitalization.characters,
              onChanged: (v) =>
                  setState(() => _draft = _draft.copyWith(divisionCode: v)),
            ),
            const SizedBox(height: 16),
          ],
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _draft.satisfies(def)
                  ? () => Navigator.of(context).pop(_draft)
                  : null,
              child: const Text('Run report'),
            ),
          ),
        ],
      ),
    );
  }

  static String _d(DateTime d) => '${d.day.toString().padLeft(2, '0')}/'
      '${d.month.toString().padLeft(2, '0')}/${d.year}';
}

/// Server-side supplier search. Debounce is unnecessary here — the list is
/// capped at 30 and the query only fires when the field settles.
class _SupplierPicker extends ConsumerStatefulWidget {
  const _SupplierPicker();

  @override
  ConsumerState<_SupplierPicker> createState() => _SupplierPickerState();
}

class _SupplierPickerState extends ConsumerState<_SupplierPicker> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final suppliers = ref.watch(reportSuppliersProvider(_query));

    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 16,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Supplier',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 12),
          TextField(
            autofocus: true,
            decoration: const InputDecoration(
              hintText: 'Search suppliers',
              prefixIcon: Icon(Icons.search_rounded),
            ),
            onSubmitted: (v) => setState(() => _query = v.trim()),
          ),
          const SizedBox(height: 8),
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.clear_all_rounded, size: 20),
            title: const Text('All suppliers'),
            onTap: () => Navigator.of(context).pop(),
          ),
          const Divider(height: 1),
          ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: MediaQuery.sizeOf(context).height * 0.4,
            ),
            child: suppliers.when(
              loading: () => const InlineLoading(),
              error: (e, _) => EmptyState(
                message: 'Could not load suppliers.\n$e',
                icon: Icons.error_outline_rounded,
              ),
              data: (list) => list.isEmpty
                  ? const EmptyState(
                      message: 'No suppliers matched.',
                      icon: Icons.search_off_rounded,
                    )
                  : ListView.separated(
                      shrinkWrap: true,
                      itemCount: list.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, i) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          list[i].label,
                          style: const TextStyle(fontSize: 14),
                        ),
                        subtitle: Text(
                          list[i].code,
                          style: const TextStyle(
                            fontSize: 11.5,
                            color: AppColors.textMuted,
                          ),
                        ),
                        onTap: () => Navigator.of(context).pop(list[i]),
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}
