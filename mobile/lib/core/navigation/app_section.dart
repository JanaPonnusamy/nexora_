import 'package:flutter/material.dart';

import 'package:nexora_mobile/core/navigation/app_capability.dart';
import 'package:nexora_mobile/core/router/app_routes.dart';

/// One tab in the bottom navigation bar.
///
/// Order here is the order on screen, and each section's index is its branch
/// index in the router's `StatefulShellRoute`. Adding a section means adding a
/// branch in the same position — see `app_router.dart`.
enum AppSection {
  home(
    label: 'Home',
    icon: Icons.dashboard_outlined,
    activeIcon: Icons.dashboard_rounded,
    path: AppRoutes.homePath,
    capability: AppCapability.home,
  ),
  capture(
    label: 'Capture',
    icon: Icons.document_scanner_outlined,
    activeIcon: Icons.document_scanner_rounded,
    path: AppRoutes.capturePath,
    capability: AppCapability.capture,
  ),
  procure(
    label: 'Procure',
    icon: Icons.inventory_2_outlined,
    activeIcon: Icons.inventory_2_rounded,
    path: AppRoutes.procurePath,
    capability: AppCapability.procurement,
  ),
  sync(
    label: 'Sync',
    icon: Icons.sync_outlined,
    activeIcon: Icons.sync_rounded,
    path: AppRoutes.syncPath,
    capability: AppCapability.sync,
  ),
  more(
    label: 'More',
    icon: Icons.more_horiz_outlined,
    activeIcon: Icons.more_horiz_rounded,
    path: AppRoutes.morePath,
    capability: AppCapability.settings,
  );

  const AppSection({
    required this.label,
    required this.icon,
    required this.activeIcon,
    required this.path,
    required this.capability,
  });

  final String label;
  final IconData icon;
  final IconData activeIcon;
  final String path;
  final AppCapability capability;

  /// Branch index in the router shell. Fixed regardless of visibility.
  int get branchIndex => index;
}
