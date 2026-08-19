import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';

/// Corner-bracket guide drawn over the camera preview.
///
/// This is a framing aid, not edge detection: it marks the region the
/// on-device quality gate actually measures, so "fill the brackets" and "the
/// page will be scored fairly" are the same instruction. Real edge detection
/// would need a native vision dependency, and the server's preprocessor
/// already deskews and crops.
class CaptureFrameOverlay extends StatelessWidget {
  const CaptureFrameOverlay({
    super.key,
    this.highlight = false,
  });

  /// Tints the brackets while a shot is being processed.
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: CustomPaint(
        painter: _FramePainter(
          color: highlight ? AppColors.accent : Colors.white,
        ),
      ),
    );
  }
}

class _FramePainter extends CustomPainter {
  const _FramePainter({required this.color});

  final Color color;

  /// Matches `_analysisCrop` in `capture_processor.dart` — the brackets must
  /// describe the region the quality gate scores, or the advice they imply is
  /// wrong.
  static const double _inset = 0.8;

  @override
  void paint(Canvas canvas, Size size) {
    final width = size.width * _inset;
    final height = size.height * _inset;
    final rect = Rect.fromCenter(
      center: Offset(size.width / 2, size.height / 2),
      width: width,
      height: height,
    );

    // Dim everything outside the frame so the eye goes to the page, using an
    // even-odd fill rather than four rectangles.
    final scrim = Path()
      ..addRect(Offset.zero & size)
      ..addRRect(RRect.fromRectAndRadius(rect, const Radius.circular(12)))
      ..fillType = PathFillType.evenOdd;
    canvas.drawPath(
        scrim, Paint()..color = Colors.black.withValues(alpha: 0.3));

    final stroke = Paint()
      ..color = color.withValues(alpha: 0.9)
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    // Corner brackets read as "aim here" without boxing the page in, which a
    // full rectangle does — users try to align edges to it and lose margin.
    final arm = width * 0.12;
    for (final corner in [
      (rect.topLeft, 1.0, 1.0),
      (rect.topRight, -1.0, 1.0),
      (rect.bottomLeft, 1.0, -1.0),
      (rect.bottomRight, -1.0, -1.0),
    ]) {
      final (origin, dx, dy) = corner;
      canvas.drawLine(origin, origin.translate(arm * dx, 0), stroke);
      canvas.drawLine(origin, origin.translate(0, arm * dy), stroke);
    }
  }

  @override
  bool shouldRepaint(_FramePainter oldDelegate) => oldDelegate.color != color;
}
