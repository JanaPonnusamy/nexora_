import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/theme/app_colors.dart';
import 'package:nexora_mobile/core/widgets/axythic_brand_mark.dart';

/// Shown while the app validates any stored session. The router replaces it as
/// soon as [AuthStatus] resolves.
class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _motion;

  @override
  void initState() {
    super.initState();
    _motion = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2200),
    )..repeat();
  }

  @override
  void dispose() {
    _motion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        fit: StackFit.expand,
        children: [
          const _SplashBackdrop(),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(28, 24, 28, 30),
              child: Column(
                children: [
                  const Spacer(flex: 5),
                  _BrandLockup(motion: _motion),
                  const Spacer(flex: 4),
                  _LoadingStatus(motion: _motion),
                  const SizedBox(height: 22),
                  const _SecurityNote(),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SplashBackdrop extends StatelessWidget {
  const _SplashBackdrop();

  @override
  Widget build(BuildContext context) {
    return const Stack(
      fit: StackFit.expand,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [Color(0xFF0D1623), AppColors.canvas, Color(0xFF070B11)],
              stops: [0, 0.48, 1],
            ),
          ),
        ),
        Positioned(
          top: -190,
          right: -170,
          child: _AmbientGlow(size: 430, color: Color(0x284F8DF7)),
        ),
        Positioned(
          left: -180,
          bottom: -225,
          child: _AmbientGlow(size: 420, color: Color(0x1800D4E8)),
        ),
        CustomPaint(painter: _BackdropPainter()),
      ],
    );
  }
}

class _AmbientGlow extends StatelessWidget {
  const _AmbientGlow({required this.size, required this.color});

  final double size;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: size,
      child: DecoratedBox(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, color.withValues(alpha: 0)],
          ),
        ),
      ),
    );
  }
}

class _BrandLockup extends StatelessWidget {
  const _BrandLockup({required this.motion});

  final Animation<double> motion;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      header: true,
      label: 'Axythic Pharma',
      child: ExcludeSemantics(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            AnimatedBuilder(
              animation: motion,
              builder: (context, child) {
                final pulse = (math.sin(motion.value * math.pi * 2) + 1) / 2;
                return Container(
                  width: 126,
                  height: 126,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: RadialGradient(
                      colors: [
                        AppColors.accent.withValues(alpha: 0.14 + pulse * 0.08),
                        AppColors.accent.withValues(alpha: 0),
                      ],
                    ),
                  ),
                  child: child,
                );
              },
              child: const ExcludeSemantics(child: AxythicBrandMark()),
            ),
            const SizedBox(height: 18),
            ShaderMask(
              blendMode: BlendMode.srcIn,
              shaderCallback: (bounds) => const LinearGradient(
                colors: [Color(0xFFEAF6FF), Color(0xFF93B8FD)],
              ).createShader(bounds),
              child: Text(
                'Axythic',
                style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                      color: Colors.white,
                      fontSize: 38,
                      height: 1,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -1.4,
                    ),
              ),
            ),
            const SizedBox(height: 11),
            const Text(
              'PHARMACY OPERATIONS, SIMPLIFIED',
              style: TextStyle(
                color: AppColors.textMuted,
                fontSize: 10.5,
                fontWeight: FontWeight.w600,
                letterSpacing: 2.1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadingStatus extends StatelessWidget {
  const _LoadingStatus({required this.motion});

  final Animation<double> motion;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      label: 'Preparing your workspace',
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 260),
        child: Container(
          height: 42,
          padding: const EdgeInsets.symmetric(horizontal: 16),
          decoration: BoxDecoration(
            color: AppColors.surface.withValues(alpha: 0.72),
            borderRadius: BorderRadius.circular(21),
            border: Border.all(color: AppColors.rule.withValues(alpha: 0.9)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              RotationTransition(
                turns: motion,
                child: const SizedBox.square(
                  dimension: 15,
                  child: CircularProgressIndicator(
                    strokeWidth: 1.8,
                    color: AppColors.accentInk,
                    backgroundColor: AppColors.rule,
                  ),
                ),
              ),
              const SizedBox(width: 11),
              const Flexible(
                child: FittedBox(
                  fit: BoxFit.scaleDown,
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Preparing your workspace',
                    maxLines: 1,
                    style: TextStyle(
                      color: AppColors.textSoft,
                      fontSize: 12.5,
                      fontWeight: FontWeight.w500,
                      letterSpacing: 0.1,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SecurityNote extends StatelessWidget {
  const _SecurityNote();

  @override
  Widget build(BuildContext context) {
    return const FittedBox(
      fit: BoxFit.scaleDown,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.lock_outline_rounded,
            size: 13,
            color: AppColors.textMuted,
          ),
          SizedBox(width: 6),
          Text(
            'Secure mobile workspace',
            maxLines: 1,
            style: TextStyle(
              color: AppColors.textMuted,
              fontSize: 11,
              letterSpacing: 0.2,
            ),
          ),
        ],
      ),
    );
  }
}

class _BackdropPainter extends CustomPainter {
  const _BackdropPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.accent.withValues(alpha: 0.045)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    final center = Offset(size.width / 2, size.height * 0.39);
    canvas.drawCircle(center, size.width * 0.42, paint);
    canvas.drawCircle(center, size.width * 0.58, paint);

    final gridPaint = Paint()
      ..color = AppColors.textMuted.withValues(alpha: 0.035)
      ..strokeWidth = 1;
    for (var x = 28.0; x < size.width; x += 52) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _BackdropPainter oldDelegate) => false;
}
