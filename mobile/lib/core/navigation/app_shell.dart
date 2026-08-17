import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/navigation/app_capability.dart';
import 'package:nexora_mobile/core/navigation/app_section.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';

/// Capabilities of the currently signed-in user.
final capabilitiesProvider = Provider<Capabilities>((ref) {
  final user = ref.watch(authControllerProvider).user;
  return Capabilities.forUser(user);
});

/// Sections the current user may see, in tab order. Never empty — Home and
/// More are not module-gated.
final visibleSectionsProvider = Provider<List<AppSection>>((ref) {
  final capabilities = ref.watch(capabilitiesProvider);
  return AppSection.values
      .where((s) => capabilities.has(s.capability))
      .toList(growable: false);
});

/// Persistent tab scaffold wrapping the router's stateful shell.
///
/// Each tab keeps its own navigation stack (an `IndexedStack` under the hood),
/// so switching away and back returns the user where they were rather than
/// resetting to the tab root.
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final visible = ref.watch(visibleSectionsProvider);

    // The shell always has all branches; only the bar is filtered. Map the
    // active branch onto its position in the visible list.
    final currentBranch = navigationShell.currentIndex;
    var selectedIndex =
        visible.indexWhere((s) => s.branchIndex == currentBranch);
    // The active branch can be one the user may not see — a deep link, or a
    // permission change mid-session. Fall back to the first visible tab rather
    // than handing NavigationBar an out-of-range index.
    if (selectedIndex < 0) selectedIndex = 0;

    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: selectedIndex,
        onDestinationSelected: (index) => _onTap(visible[index]),
        destinations: [
          for (final section in visible)
            NavigationDestination(
              icon: Icon(section.icon),
              selectedIcon: Icon(section.activeIcon),
              label: section.label,
              tooltip: section.label,
            ),
        ],
      ),
    );
  }

  void _onTap(AppSection section) {
    // `initialLocation: true` when re-tapping the active tab pops that tab back
    // to its root, which is the platform-standard gesture on both iOS and
    // Android.
    navigationShell.goBranch(
      section.branchIndex,
      initialLocation: section.branchIndex == navigationShell.currentIndex,
    );
  }
}
