import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/reports/domain/report_formatting.dart';

/// One extracted line.
///
/// A card, not a grid row. The desktop console can show fourteen columns; a
/// phone cannot, and a line the reviewer has to scroll sideways to read is a
/// line they will not check. So each line leads with what identifies it, then
/// the four numbers that decide whether it is right, then why it is flagged.
class ReviewItemCard extends StatelessWidget {
  const ReviewItemCard({
    super.key,
    required this.item,
    required this.findings,
    required this.onEdit,
    required this.onExclude,
    this.readOnly = false,
  });

  final DocumentItem item;

  /// Server findings attached to this line, so a warning sits on the line it
  /// is about instead of in a list the reviewer has to match up by hand.
  final List<ValidationFinding> findings;

  final VoidCallback onEdit;
  final VoidCallback onExclude;
  final bool readOnly;

  @override
  Widget build(BuildContext context) {
    final highlights = item.highlights();
    final excluded = item.isExcluded;
    final tone = excluded
        ? AppColors.textMuted
        : findings.any((f) => f.isError)
            ? AppColors.danger
            : highlights.isEmpty
                ? AppColors.rule
                : AppColors.warning;

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Opacity(
        opacity: excluded ? 0.55 : 1,
        child: StatusCard(
          accentColor: tone,
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _LineNumber(number: item.lineNumber),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          item.displayName,
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w700,
                            decoration:
                                excluded ? TextDecoration.lineThrough : null,
                          ),
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                        ),
                        if (item.productCode != null || item.pack != null) ...[
                          const SizedBox(height: 3),
                          Text(
                            [
                              if (item.productCode != null) item.productCode!,
                              if (item.pack != null) 'Pack ${item.pack}',
                              if (item.hsnCode != null) 'HSN ${item.hsnCode}',
                            ].join(' · '),
                            style: const TextStyle(
                              fontSize: 11.5,
                              color: AppColors.textMuted,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    item.amount == null
                        ? '—'
                        : ReportFormatter.money(item.amount),
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                      color: item.amount == null
                          ? AppColors.textMuted
                          : AppColors.text,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              _facts(),
              if (excluded) ...[
                const SizedBox(height: 10),
                const InfoChip(
                  label: 'Not part of this invoice',
                  icon: Icons.block_rounded,
                ),
              ] else ...[
                if (highlights.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final flag in highlights)
                        InfoChip(
                          label: flag,
                          icon: Icons.flag_outlined,
                          color: AppColors.warning,
                        ),
                    ],
                  ),
                ],
                for (final finding in findings)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(
                          finding.isError
                              ? Icons.error_outline_rounded
                              : Icons.info_outline_rounded,
                          size: 14,
                          color: finding.isError
                              ? AppColors.dangerInk
                              : AppColors.warningInk,
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            finding.message,
                            style: const TextStyle(
                              fontSize: 12,
                              height: 1.3,
                              color: AppColors.textSoft,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                if (!readOnly) ...[
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      TextButton.icon(
                        onPressed: onEdit,
                        icon: const Icon(Icons.edit_outlined, size: 15),
                        label: const Text('Edit line'),
                        style: _actionStyle(AppColors.accentInk),
                      ),
                      const Spacer(),
                      TextButton.icon(
                        onPressed: onExclude,
                        icon: const Icon(Icons.block_rounded, size: 15),
                        label: const Text('Remove'),
                        style: _actionStyle(AppColors.textMuted),
                      ),
                    ],
                  ),
                ],
              ],
            ],
          ),
        ),
      ),
    );
  }

  static ButtonStyle _actionStyle(Color color) => TextButton.styleFrom(
        foregroundColor: color,
        // Explicit, because the app theme's Size.fromHeight would force an
        // infinite width inside this Row and assert at layout time.
        minimumSize: const Size(0, 34),
        padding: const EdgeInsets.symmetric(horizontal: 10),
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        textStyle: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600),
      );

  /// Batch, expiry, quantity and rate: the four values a purchase clerk checks
  /// against the paper before anything else.
  Widget _facts() {
    return Wrap(
      spacing: 16,
      runSpacing: 8,
      children: [
        _Fact(
          label: 'Batch',
          value: item.batchNumber,
          warn: item.hasInvalidBatch,
        ),
        _Fact(
          label: 'Expiry',
          value: item.expiryDate != null
              ? ReportFormatter.date(item.expiryDate)
              : item.expiryRaw,
          warn: item.hasExpiryProblem(),
        ),
        _Fact(
          label: 'Qty',
          value: item.quantity == null
              ? null
              : [
                  ReportFormatter.integer(item.quantity),
                  if ((item.freeQuantity ?? 0) > 0)
                    '+${ReportFormatter.integer(item.freeQuantity)} free',
                ].join(' '),
        ),
        _Fact(
          label: 'Rate',
          value: item.purchaseRate == null && item.ptr == null
              ? null
              : ReportFormatter.money(item.purchaseRate ?? item.ptr),
        ),
        if (item.ptr != null && item.purchaseRate != null)
          _Fact(
            label: 'PTR',
            value: ReportFormatter.money(item.ptr),
          ),
        _Fact(
          label: 'MRP',
          value: item.mrp == null ? null : ReportFormatter.money(item.mrp),
        ),
        if (item.gstPercent != null)
          _Fact(
              label: 'GST',
              value: '${ReportFormatter.integer(
                item.gstPercent,
              )}%'),
        if (item.discountPercent != null)
          _Fact(
            label: 'PDisc',
            value: '${ReportFormatter.integer(item.discountPercent)}%',
          ),
      ],
    );
  }
}

class _Fact extends StatelessWidget {
  const _Fact({required this.label, required this.value, this.warn = false});

  final String label;
  final String? value;
  final bool warn;

  @override
  Widget build(BuildContext context) {
    final missing = value == null || value!.isEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 10.5, color: AppColors.textMuted),
        ),
        const SizedBox(height: 2),
        Text(
          missing ? '—' : value!,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w600,
            color: warn
                ? AppColors.warningInk
                : missing
                    ? AppColors.textMuted
                    : AppColors.text,
          ),
        ),
      ],
    );
  }
}

class _LineNumber extends StatelessWidget {
  const _LineNumber({required this.number});

  final int number;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 26,
      height: 26,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.surfaceSunk,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.rule),
      ),
      child: Text(
        '$number',
        style: const TextStyle(
          fontSize: 11.5,
          fontWeight: FontWeight.w700,
          color: AppColors.textMuted,
        ),
      ),
    );
  }
}
