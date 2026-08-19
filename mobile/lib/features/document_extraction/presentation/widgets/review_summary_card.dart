import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/mobile_components.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';
import 'package:nexora_mobile/features/reports/domain/report_formatting.dart';

/// The verdict on the whole invoice: what the server's rules found, and
/// whether the document adds up.
///
/// It leads the screen because the reviewer's first question is "can I trust
/// this?", and the answer decides whether they skim or read every line.
class ReviewSummaryCard extends StatelessWidget {
  const ReviewSummaryCard({super.key, required this.review});

  final DocumentReview review;

  @override
  Widget build(BuildContext context) {
    final errors = review.errorCount;
    final warnings = review.warningCount;
    final mismatched =
        review.reconciliation.where((c) => !c.balanced).toList(growable: false);

    final tone = errors > 0
        ? AppColors.danger
        : warnings > 0 || mismatched.isNotEmpty
            ? AppColors.warning
            : AppColors.success;

    return StatusCard(
      accentColor: tone,
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  _headline(errors, warnings, mismatched.length),
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: tone == AppColors.success
                        ? AppColors.successInk
                        : tone == AppColors.warning
                            ? AppColors.warningInk
                            : AppColors.dangerInk,
                  ),
                ),
              ),
              StatusBadge(
                label: review.status.label,
                color:
                    review.isCommitted ? AppColors.success : AppColors.accent,
                dense: true,
              ),
            ],
          ),
          if (review.validationStatus == ValidationStatus.pending)
            const Padding(
              padding: EdgeInsets.only(top: 6),
              child: Text(
                // Distinguishing "checked and clean" from "never checked"
                // matters: the second is not a pass.
                'This invoice has not been checked yet.',
                style: TextStyle(fontSize: 12.5, color: AppColors.textMuted),
              ),
            ),
          if (review.headerFindings.isNotEmpty) ...[
            const SizedBox(height: 12),
            for (final finding in _ordered(review.headerFindings))
              _Finding(finding: finding),
          ],
          if (review.reconciliation.isNotEmpty) ...[
            const SizedBox(height: 14),
            const Divider(height: 1, color: AppColors.rule),
            const SizedBox(height: 12),
            const Text(
              'DOES IT ADD UP',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w700,
                letterSpacing: 0.6,
                color: AppColors.textMuted,
              ),
            ),
            const SizedBox(height: 8),
            for (final check in review.reconciliation) _Check(check: check),
          ],
        ],
      ),
    );
  }

  /// Errors first, so the one thing blocking a save is not below three
  /// warnings about batch numbers.
  static List<ValidationFinding> _ordered(List<ValidationFinding> findings) =>
      [...findings]..sort(
          (a, b) => (b.isError ? 1 : 0).compareTo(a.isError ? 1 : 0),
        );

  static String _headline(int errors, int warnings, int mismatches) {
    if (errors == 0 && warnings == 0 && mismatches == 0) {
      return 'Everything checks out';
    }
    final parts = <String>[
      if (errors > 0) '$errors error${errors == 1 ? '' : 's'}',
      if (warnings > 0) '$warnings warning${warnings == 1 ? '' : 's'}',
      if (mismatches > 0)
        mismatches == 1
            ? '1 total that does not match'
            : '$mismatches totals that do not match',
    ];
    return parts.join(' · ');
  }
}

class _Finding extends StatelessWidget {
  const _Finding({required this.finding});

  final ValidationFinding finding;

  @override
  Widget build(BuildContext context) {
    final colour = finding.isError ? AppColors.dangerInk : AppColors.warningInk;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            finding.isError
                ? Icons.error_outline_rounded
                : Icons.warning_amber_rounded,
            size: 15,
            color: colour,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  finding.message,
                  style: const TextStyle(
                    fontSize: 12.5,
                    height: 1.35,
                    color: AppColors.textSoft,
                  ),
                ),
                if (finding.expected != null || finding.actual != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      'Expected ${finding.expected ?? '—'}, '
                      'found ${finding.actual ?? '—'}',
                      style: const TextStyle(
                        fontSize: 11.5,
                        color: AppColors.textMuted,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Check extends StatelessWidget {
  const _Check({required this.check});

  final ReconcileCheck check;

  String _value(double amount) => check.money
      ? ReportFormatter.money(amount)
      : ReportFormatter.integer(amount);

  @override
  Widget build(BuildContext context) {
    final colour = check.balanced ? AppColors.successInk : AppColors.warningInk;

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Icon(
            check.balanced
                ? Icons.check_circle_outline_rounded
                : Icons.report_problem_outlined,
            size: 15,
            color: colour,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              check.label,
              style: const TextStyle(fontSize: 12.5, color: AppColors.textSoft),
            ),
          ),
          Text(
            check.balanced
                ? _value(check.extracted)
                // Both figures, because "off by 40" is only useful next to the
                // two numbers it came from.
                : '${_value(check.computed)} vs ${_value(check.extracted)}',
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: check.balanced ? AppColors.textSoft : colour,
            ),
          ),
        ],
      ),
    );
  }
}
