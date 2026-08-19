import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/reports/domain/report_formatting.dart';
import 'package:nexora_mobile/features/reports/domain/report_models.dart';

/// One report row, as a card rather than a table row.
///
/// The desktop reports are 8-16 column grids. Reproducing that on a phone
/// yields a horizontally scrolling table nobody reads; the card leads with the
/// row's identity and lays the numbers out in a wrapping label/value grid, so
/// the whole row is legible without sideways scrolling.
class ReportRowCard extends StatelessWidget {
  const ReportRowCard({
    super.key,
    required this.row,
    required this.result,
    this.index,
  });

  final Map<String, dynamic> row;
  final ReportResult result;
  final int? index;

  @override
  Widget build(BuildContext context) {
    final primary = result.primaryColumn;
    final details = result.detailColumns;

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.rule),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (primary != null)
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    ReportFormatter.cell(row[primary.key], primary),
                    style: const TextStyle(
                      fontSize: 13.5,
                      fontWeight: FontWeight.w700,
                      height: 1.3,
                    ),
                  ),
                ),
                if (index != null)
                  Padding(
                    padding: const EdgeInsets.only(left: 8, top: 2),
                    child: Text(
                      '#${index! + 1}',
                      style: const TextStyle(
                        fontSize: 11,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
              ],
            ),
          if (details.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 16,
              runSpacing: 8,
              children: [
                for (final column in details)
                  if (row[column.key] != null)
                    _Field(column: column, value: row[column.key]),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.column, required this.value});

  final ReportColumn column;
  final Object? value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          column.label,
          style: const TextStyle(fontSize: 10.5, color: AppColors.textMuted),
        ),
        const SizedBox(height: 1),
        Text(
          ReportFormatter.cell(value, column),
          style: TextStyle(
            fontSize: 13,
            // Numbers get the tabular weight; text stays regular so a card of
            // mostly-text columns does not read as all-caps emphasis.
            fontWeight: column.isNumeric ? FontWeight.w700 : FontWeight.w500,
            fontFeatures:
                column.isNumeric ? const [FontFeature.tabularFigures()] : null,
          ),
        ),
      ],
    );
  }
}

/// The optional totals row, pinned above the list.
class ReportSummaryCard extends StatelessWidget {
  const ReportSummaryCard({super.key, required this.result});

  final ReportResult result;

  @override
  Widget build(BuildContext context) {
    final summary = result.summary;
    if (summary == null || summary.isEmpty) return const SizedBox.shrink();

    // Only show summary keys that correspond to a real column, so an internal
    // bookkeeping field never leaks into the UI as a mystery number.
    final fields = <(ReportColumn, Object?)>[
      for (final column in result.columns)
        if (summary.containsKey(column.key)) (column, summary[column.key]),
    ];
    if (fields.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.accentSunk,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'TOTALS',
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.4,
              color: AppColors.accentInk,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 18,
            runSpacing: 8,
            children: [
              for (final (column, value) in fields)
                _Field(column: column, value: value),
            ],
          ),
        ],
      ),
    );
  }
}
