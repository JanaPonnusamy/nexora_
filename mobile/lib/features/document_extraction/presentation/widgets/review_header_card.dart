import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/reports/domain/report_formatting.dart';

/// Supplier, invoice identity and the money — the part of the document a
/// reviewer checks before looking at a single line.
///
/// Two edit affordances rather than one form: identity and amounts are read
/// off different corners of a page and corrected at different moments.
class ReviewHeaderCard extends StatelessWidget {
  const ReviewHeaderCard({
    super.key,
    required this.review,
    required this.onEditDetails,
    required this.onEditAmounts,
    required this.onAssignSupplier,
    this.readOnly = false,
  });

  final DocumentReview review;
  final VoidCallback onEditDetails;
  final VoidCallback onEditAmounts;
  final VoidCallback onAssignSupplier;

  /// A saved invoice is shown, not edited.
  final bool readOnly;

  @override
  Widget build(BuildContext context) {
    final header = review.header;
    final supplier = review.supplier;

    return StatusCard(
      accentColor: supplier.isUnknown ? AppColors.warning : AppColors.accent,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _supplier(supplier),
          const _Divider(),
          _SectionRow(
            title: 'Invoice',
            onEdit: readOnly ? null : onEditDetails,
          ),
          const SizedBox(height: 8),
          // The three fields the server refuses to save without. Marking them
          // here means the reviewer sees the gap where the value belongs,
          // rather than only as a finding further down the screen.
          ReviewDetailRow(
            label: 'Invoice number',
            value: header.invoiceNumber,
            required: true,
          ),
          ReviewDetailRow(
            label: 'Invoice date',
            value: header.invoiceDate == null
                ? null
                : ReportFormatter.date(header.invoiceDate),
            required: true,
          ),
          if (header.invoiceType != null)
            ReviewDetailRow(label: 'Type', value: header.invoiceType),
          if (header.orderNumber != null)
            ReviewDetailRow(label: 'Order number', value: header.orderNumber),
          const _Divider(),
          _SectionRow(
            title: 'Amounts',
            onEdit: readOnly ? null : onEditAmounts,
          ),
          const SizedBox(height: 8),
          if (header.grossAmount != null)
            ReviewDetailRow(
              label: 'Gross',
              value: ReportFormatter.money(header.grossAmount),
            ),
          if (header.discountAmount != null)
            ReviewDetailRow(
              label: 'Discount',
              value: ReportFormatter.money(header.discountAmount),
            ),
          if (header.taxableAmount != null)
            ReviewDetailRow(
              label: 'Taxable',
              value: ReportFormatter.money(header.taxableAmount),
            ),
          if (_tax(header) != null)
            ReviewDetailRow(label: 'GST', value: _tax(header)),
          if (header.roundOff != null)
            ReviewDetailRow(
              label: 'Round off',
              value: ReportFormatter.money(header.roundOff),
            ),
          ReviewDetailRow(
            label: 'Net amount',
            value: header.netAmount == null
                ? null
                : ReportFormatter.money(header.netAmount),
            required: true,
            emphasise: true,
          ),
        ],
      ),
    );
  }

  /// One line for the three GST components: on a phone, three near-identical
  /// rows of tax cost more attention than they return.
  static String? _tax(DocumentHeader header) {
    final parts = <String>[
      if (header.cgstAmount != null)
        'CGST ${ReportFormatter.money(header.cgstAmount)}',
      if (header.sgstAmount != null)
        'SGST ${ReportFormatter.money(header.sgstAmount)}',
      if (header.igstAmount != null)
        'IGST ${ReportFormatter.money(header.igstAmount)}',
    ];
    return parts.isEmpty ? null : parts.join(' · ');
  }

  Widget _supplier(DocumentSupplier supplier) {
    final confidence = supplier.matchConfidence;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Text(
                supplier.supplierName ?? 'Supplier not identified',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: supplier.supplierName == null
                      ? AppColors.warningInk
                      : AppColors.text,
                ),
              ),
            ),
            if (!readOnly)
              TextButton(
                onPressed: onAssignSupplier,
                style: TextButton.styleFrom(
                  minimumSize: const Size(0, 32),
                  padding: const EdgeInsets.symmetric(horizontal: 10),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: Text(supplier.isUnknown ? 'Assign' : 'Change'),
              ),
          ],
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            if (supplier.isUnknown)
              const InfoChip(
                label: 'Not matched to a supplier',
                icon: Icons.help_outline_rounded,
                color: AppColors.warning,
              )
            else if (supplier.matchMethod != null)
              InfoChip(
                // How it matched is the reviewer's shortcut: a GST match is
                // worth a glance, a name match is worth a check.
                label: confidence == null
                    ? 'Matched on ${supplier.matchMethod}'
                    : 'Matched on ${supplier.matchMethod} · '
                        '${(confidence * 100).round()}%',
                icon: Icons.verified_outlined,
                color: confidence != null && confidence < 0.75
                    ? AppColors.warning
                    : AppColors.success,
              ),
            if (supplier.matchedSupplierCode != null)
              InfoChip(label: supplier.matchedSupplierCode!),
            if (supplier.gstNumber != null)
              InfoChip(label: 'GST ${supplier.gstNumber}'),
            if (supplier.dlNumber != null)
              InfoChip(label: 'DL ${supplier.dlNumber}'),
          ],
        ),
      ],
    );
  }
}

/// Label on the left, value on the right. Missing values read as a gap to
/// fill, not as a zero.
class ReviewDetailRow extends StatelessWidget {
  const ReviewDetailRow({
    super.key,
    required this.label,
    required this.value,
    this.required = false,
    this.emphasise = false,
  });

  final String label;
  final String? value;

  /// The server will not save without it, so an empty one is shown in warning
  /// colour rather than as a neutral dash.
  final bool required;

  final bool emphasise;

  @override
  Widget build(BuildContext context) {
    final missing = value == null || value!.isEmpty;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 4,
            child: Text(
              label,
              style:
                  const TextStyle(fontSize: 12.5, color: AppColors.textMuted),
            ),
          ),
          Expanded(
            flex: 6,
            child: Text(
              missing ? (required ? 'Missing' : '—') : value!,
              textAlign: TextAlign.right,
              style: TextStyle(
                fontSize: emphasise ? 15 : 13,
                fontWeight: emphasise ? FontWeight.w800 : FontWeight.w600,
                color: missing
                    ? (required ? AppColors.warningInk : AppColors.textMuted)
                    : AppColors.text,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionRow extends StatelessWidget {
  const _SectionRow({required this.title, this.onEdit});

  final String title;
  final VoidCallback? onEdit;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Text(
            title.toUpperCase(),
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.6,
              color: AppColors.textMuted,
            ),
          ),
        ),
        if (onEdit != null)
          TextButton.icon(
            onPressed: onEdit,
            icon: const Icon(Icons.edit_outlined, size: 15),
            label: const Text('Edit'),
            style: TextButton.styleFrom(
              minimumSize: const Size(0, 30),
              padding: const EdgeInsets.symmetric(horizontal: 8),
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              textStyle: const TextStyle(
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
      ],
    );
  }
}

class _Divider extends StatelessWidget {
  const _Divider();

  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.symmetric(vertical: 12),
        child: Divider(height: 1, color: AppColors.rule),
      );
}
