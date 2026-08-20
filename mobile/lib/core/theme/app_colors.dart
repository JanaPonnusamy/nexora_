import 'package:flutter/material.dart';

/// Axythic brand palette for mobile — **dark only**.
///
/// Values mirror the dark half of the web design system
/// (`frontend/src/design-system/tokens/theme.ts`) so the mobile app and the HO
/// console read as one product. Names match the web's semantic token names
/// (`--nx-*`) rather than Material's, so a token can be traced across surfaces.
///
/// There is deliberately no light set: the product ships a single dark theme.
class AppColors {
  AppColors._();

  // ---------------------------------------------------------------------------
  // Surfaces — darkest (canvas) to lightest (raised), plus interaction states.
  // ---------------------------------------------------------------------------

  /// App background, behind everything.
  static const Color canvas = Color(0xFF0A0F17);

  /// Default card / sheet background.
  static const Color surface = Color(0xFF111823);

  /// Elevated surfaces: dialogs, bottom sheets, sticky headers.
  static const Color surfaceRaised = Color(0xFF17202D);

  /// Recessed wells: input fills, code blocks, inset lists.
  static const Color surfaceSunk = Color(0xFF0D141E);

  /// Pressed / hovered row background.
  static const Color surfaceHover = Color(0xFF1A2331);

  // ---------------------------------------------------------------------------
  // Rules — hairlines and dividers.
  // ---------------------------------------------------------------------------

  static const Color rule = Color(0xFF212C3A);
  static const Color ruleStrong = Color(0xFF32404F);

  // ---------------------------------------------------------------------------
  // Text — three weights of emphasis, all AA-contrast on [surface].
  // ---------------------------------------------------------------------------

  /// Primary body and headings.
  static const Color text = Color(0xFFE7EDF5);

  /// Secondary text: subtitles, descriptions.
  static const Color textSoft = Color(0xFFB6C2D2);

  /// Tertiary text: captions, timestamps, placeholders.
  static const Color textMuted = Color(0xFF8494A8);

  /// Text on a filled accent/status surface.
  static const Color textOn = Color(0xFFFFFFFF);

  // ---------------------------------------------------------------------------
  // Accent — the primary interactive colour.
  // ---------------------------------------------------------------------------

  static const Color accent = Color(0xFF4F8DF7);
  static const Color accentHover = Color(0xFF6D9FFF);

  /// Tinted background for selected/active states.
  static const Color accentSunk = Color(0xFF15243D);

  /// Accent-coloured text/icons on a dark background.
  static const Color accentInk = Color(0xFF93B8FD);

  // ---------------------------------------------------------------------------
  // Status — each has a base (fill/border), sunk (tinted bg) and ink (text).
  // ---------------------------------------------------------------------------

  static const Color success = Color(0xFF10B981);
  static const Color successSunk = Color(0xFF0C2A22);
  static const Color successInk = Color(0xFF4ADE94);

  static const Color warning = Color(0xFFF59E0B);
  static const Color warningSunk = Color(0xFF2E2210);
  static const Color warningInk = Color(0xFFFBBF24);

  static const Color danger = Color(0xFFEF4444);
  static const Color dangerSunk = Color(0xFF331618);
  static const Color dangerInk = Color(0xFFFCA5A5);

  static const Color info = Color(0xFF22B8CF);
  static const Color infoSunk = Color(0xFF0C2830);
  static const Color infoInk = Color(0xFF67E8F9);

  // ---------------------------------------------------------------------------
  // Effects.
  // ---------------------------------------------------------------------------

  /// Focus ring for keyboard/accessibility traversal.
  static const Color focus = Color(0x736D9FFF);

  /// Modal/drawer backdrop.
  static const Color scrim = Color(0xA802060C);

  // ---------------------------------------------------------------------------
  // Brand gradients — from `frontend/src/assets/axythic-logo.svg`.
  // Used for the splash, app icon and hero surfaces only; never for UI chrome.
  // ---------------------------------------------------------------------------

  /// The logo's left face: light blue → deep navy.
  static const List<Color> brandBlue = <Color>[
    Color(0xFF42B4F5),
    Color(0xFF1976D2),
    Color(0xFF0D3A8A),
  ];

  /// The logo's centre-right face: cyan → violet → magenta → orange.
  static const List<Color> brandSpectrum = <Color>[
    Color(0xFF00D4E8),
    Color(0xFF8B3FD9),
    Color(0xFFE82070),
    Color(0xFFFF6010),
  ];

  /// Stops matching [brandSpectrum]'s distribution in the source SVG.
  static const List<double> brandSpectrumStops = <double>[0.0, 0.28, 0.62, 1.0];
}
