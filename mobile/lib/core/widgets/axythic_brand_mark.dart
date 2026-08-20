import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';

/// The faceted Axythic emblem, rendered as a resolution-independent vector.
class AxythicBrandMark extends StatelessWidget {
  const AxythicBrandMark({
    super.key,
    this.width = 84,
    this.height = 92,
  });

  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      image: true,
      label: 'Axythic',
      child: CustomPaint(
        size: Size(width, height),
        painter: const _BrandMarkPainter(),
      ),
    );
  }
}

class _BrandMarkPainter extends CustomPainter {
  const _BrandMarkPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final sx = size.width / 78;
    final sy = size.height / 88;
    Offset point(double x, double y) => Offset(x * sx, y * sy);

    final leftFace = Path()
      ..moveTo(point(39, 4).dx, point(39, 4).dy)
      ..lineTo(point(3, 84).dx, point(3, 84).dy)
      ..lineTo(point(21, 84).dx, point(21, 84).dy)
      ..lineTo(point(39, 57).dx, point(39, 57).dy)
      ..close();
    final spectrumFace = Path()
      ..moveTo(point(39, 4).dx, point(39, 4).dy)
      ..lineTo(point(52, 4).dx, point(52, 4).dy)
      ..lineTo(point(73, 84).dx, point(73, 84).dy)
      ..lineTo(point(57, 84).dx, point(57, 84).dy)
      ..lineTo(point(39, 57).dx, point(39, 57).dy)
      ..close();
    final edge = Path()
      ..moveTo(point(52, 4).dx, point(52, 4).dy)
      ..lineTo(point(55, 4).dx, point(55, 4).dy)
      ..lineTo(point(75, 84).dx, point(75, 84).dy)
      ..lineTo(point(73, 84).dx, point(73, 84).dy)
      ..close();

    canvas.drawShadow(leftFace, const Color(0xCC1976D2), 18, false);
    canvas.drawShadow(spectrumFace, const Color(0x668B3FD9), 14, false);
    canvas.drawPath(
      leftFace,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomLeft,
          colors: AppColors.brandBlue,
        ).createShader(Offset.zero & size),
    );
    canvas.drawPath(
      spectrumFace,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomRight,
          colors: AppColors.brandSpectrum,
          stops: AppColors.brandSpectrumStops,
        ).createShader(Offset.zero & size),
    );
    canvas.drawPath(
      edge,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [Color(0xFFA8D4F0), Color(0xFF4D7490)],
        ).createShader(Offset.zero & size),
    );

    canvas.drawOval(
      Rect.fromCenter(center: point(44, 11), width: 18 * sx, height: 10 * sy),
      Paint()
        ..shader = RadialGradient(
          colors: [
            Colors.white.withValues(alpha: 0.65),
            Colors.white.withValues(alpha: 0),
          ],
        ).createShader(
          Rect.fromCircle(center: point(44, 11), radius: 10 * sx),
        ),
    );
  }

  @override
  bool shouldRepaint(covariant _BrandMarkPainter oldDelegate) => false;
}
