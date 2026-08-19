import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/document_extraction/domain/capture_quality.dart';

/// Verdict shown over the viewfinder immediately after a shot.
///
/// It offers a retake but never demands one — see the note in
/// `capture_quality.dart`: the heuristics can be wrong about a faded thermal
/// invoice that is nevertheless the only copy in existence.
class QualityBanner extends StatelessWidget {
  const QualityBanner({
    super.key,
    required this.quality,
    required this.onRetake,
    required this.onDismiss,
  });

  final CaptureQuality quality;
  final VoidCallback onRetake;
  final VoidCallback onDismiss;

  Color get _color => switch (quality.verdict) {
        QualityVerdict.good => AppColors.success,
        QualityVerdict.warn => AppColors.warning,
        QualityVerdict.reject => AppColors.danger,
      };

  IconData get _icon => switch (quality.verdict) {
        QualityVerdict.good => Icons.check_circle_rounded,
        QualityVerdict.warn => Icons.info_rounded,
        QualityVerdict.reject => Icons.error_rounded,
      };

  @override
  Widget build(BuildContext context) {
    final issue = quality.primaryIssue;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12),
      padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
      decoration: BoxDecoration(
        color: AppColors.surfaceRaised.withValues(alpha: 0.96),
        borderRadius: BorderRadius.circular(AppTheme.radiusMd),
        border: Border.all(color: _color.withValues(alpha: 0.5)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(_icon, size: 18, color: _color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  quality.headline,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: _color,
                  ),
                ),
                if (issue != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      issue.advice,
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
          const SizedBox(width: 4),
          if (quality.verdict.needsAttention)
            TextButton(
              onPressed: onRetake,
              style: TextButton.styleFrom(
                foregroundColor: _color,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                minimumSize: const Size(0, 36),
                tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
              child: const Text('Retake'),
            ),
          IconButton(
            onPressed: onDismiss,
            icon: const Icon(Icons.close_rounded, size: 18),
            color: AppColors.textMuted,
            visualDensity: VisualDensity.compact,
            tooltip: 'Dismiss',
          ),
        ],
      ),
    );
  }
}
