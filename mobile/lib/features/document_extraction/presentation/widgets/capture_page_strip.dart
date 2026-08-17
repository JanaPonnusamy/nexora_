import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_session_controller.dart';
import 'package:nexora_mobile/features/document_extraction/domain/capture_quality.dart';

/// Filmstrip of the pages captured so far, newest last.
///
/// Shown over the viewfinder so the page count and the state of each shot stay
/// visible while shooting — a multi-page invoice is the normal case, and
/// discovering on the review screen that page 3 was never taken means going
/// back to the supplier.
class CapturePageStrip extends StatelessWidget {
  const CapturePageStrip({
    super.key,
    required this.pages,
    required this.onRemove,
    this.onTap,
  });

  final List<CapturedPage> pages;
  final void Function(int index) onRemove;
  final void Function(int index)? onTap;

  @override
  Widget build(BuildContext context) {
    if (pages.isEmpty) return const SizedBox.shrink();

    return SizedBox(
      height: 76,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: pages.length,
        separatorBuilder: (_, __) => const SizedBox(width: 8),
        itemBuilder: (context, index) => _Thumbnail(
          page: pages[index],
          pageNumber: index + 1,
          onRemove: () => onRemove(index),
          onTap: onTap == null ? null : () => onTap!(index),
        ),
      ),
    );
  }
}

class _Thumbnail extends StatelessWidget {
  const _Thumbnail({
    required this.page,
    required this.pageNumber,
    required this.onRemove,
    this.onTap,
  });

  final CapturedPage page;
  final int pageNumber;
  final VoidCallback onRemove;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final verdict = page.quality.verdict;
    final border = switch (verdict) {
      QualityVerdict.good => AppColors.rule,
      QualityVerdict.warn => AppColors.warning,
      QualityVerdict.reject => AppColors.danger,
    };

    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: 58,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: 58,
              height: 76,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: border, width: 1.5),
                color: AppColors.surfaceSunk,
              ),
              clipBehavior: Clip.antiAlias,
              // Thumbnails are decoded at display size: a filmstrip of ten
              // full-resolution pages would otherwise hold ~200 MB of decoded
              // bitmap in the image cache and get the app killed mid-capture.
              child: Image.file(
                page.file,
                fit: BoxFit.cover,
                cacheWidth: 174,
                gaplessPlayback: true,
                errorBuilder: (_, __, ___) => const Icon(
                  Icons.broken_image_outlined,
                  size: 18,
                  color: AppColors.textMuted,
                ),
              ),
            ),
            Positioned(
              left: 0,
              bottom: 0,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.7),
                  borderRadius: const BorderRadius.only(
                    topRight: Radius.circular(6),
                    bottomLeft: Radius.circular(7),
                  ),
                ),
                child: Text(
                  '$pageNumber',
                  style: const TextStyle(
                    fontSize: 10.5,
                    fontWeight: FontWeight.w700,
                    color: Colors.white,
                  ),
                ),
              ),
            ),
            if (verdict.needsAttention)
              Positioned(
                left: 4,
                top: 4,
                child: Icon(
                  verdict == QualityVerdict.reject
                      ? Icons.error_rounded
                      : Icons.info_rounded,
                  size: 14,
                  color: border,
                  shadows: const [Shadow(blurRadius: 3, color: Colors.black)],
                ),
              ),
            Positioned(
              right: -6,
              top: -6,
              child: GestureDetector(
                onTap: onRemove,
                behavior: HitTestBehavior.opaque,
                child: Container(
                  padding: const EdgeInsets.all(3),
                  decoration: const BoxDecoration(
                    color: AppColors.surfaceRaised,
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(
                    Icons.close_rounded,
                    size: 13,
                    color: AppColors.textSoft,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
