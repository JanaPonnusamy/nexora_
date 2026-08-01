import 'package:flutter/material.dart';

/// Brand palette for Nexora mobile. Kept as a single source so light/dark
/// schemes and custom widgets stay consistent.
class AppColors {
  AppColors._();

  // Primary brand — deep indigo/blue used across the Nexora surfaces.
  static const Color primary = Color(0xFF2547D0);
  static const Color primaryDark = Color(0xFF1B2E8A);
  static const Color primaryLight = Color(0xFF5B78F0);

  static const Color accent = Color(0xFF00B5A5);

  static const Color success = Color(0xFF2E9E5B);
  static const Color warning = Color(0xFFE0A100);
  static const Color error = Color(0xFFD64545);

  // Neutrals
  static const Color ink = Color(0xFF141824);
  static const Color slate = Color(0xFF5A6273);
  static const Color line = Color(0xFFE2E5EC);
  static const Color surfaceLight = Color(0xFFF6F7FB);
  static const Color surfaceDark = Color(0xFF12141C);
  static const Color cardDark = Color(0xFF1B1E2A);
}
