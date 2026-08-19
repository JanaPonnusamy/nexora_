import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/security/app_lock_controller.dart';
import 'package:nexora_mobile/core/security/presentation/app_lock_screen.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';

/// Puts the lock screen over the whole app when it is locked.
///
/// Installed via `MaterialApp.router`'s `builder`, not as a route, for two
/// reasons: it covers screens pushed onto the root navigator (the camera) that
/// a shell route would not, and it cannot be navigated out of — a lock that
/// yields to a back gesture is not a lock.
///
/// The router keeps running underneath. Locking is not signing out: the sync
/// engine and the capture upload queue carry on behind the cover, which is the
/// whole point of a queue that drains on reconnect.
class AppLockGate extends ConsumerStatefulWidget {
  const AppLockGate({super.key, required this.child});

  final Widget child;

  @override
  ConsumerState<AppLockGate> createState() => _AppLockGateState();
}

class _AppLockGateState extends ConsumerState<AppLockGate>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    ref.read(appLockControllerProvider.notifier).onLifecycleChange(state);

    // Coming back to the app is the moment to push anything still owed. The
    // outbox already drains on a connectivity change, but a phone that was
    // offline in a pocket and is now on the shop wi-fi may produce no such
    // event — the OS reconnected while the app was suspended. Without this the
    // user waits for the five-minute sweep to notice.
    if (state == AppLifecycleState.resumed) {
      ref.read(outboxCoordinatorProvider).drainNow();
    }
  }

  @override
  Widget build(BuildContext context) {
    final lock = ref.watch(appLockControllerProvider);
    final signedIn = ref.watch(
      authControllerProvider.select((s) => s.isAuthenticated),
    );

    // There is nothing to protect before a session exists, and covering the
    // login screen with an unlock prompt would be a dead end for anyone who
    // signed out with the lock on.
    final showLock = lock.locked && signedIn;

    return Stack(
      children: [
        widget.child,
        if (showLock)
          // Opaque, and above everything. TickerMode keeps the covered tree from
          // animating out of sight — an indeterminate progress bar under the
          // lock screen would otherwise spin for as long as the phone is in
          // someone's pocket.
          const Positioned.fill(
            child: TickerMode(
              enabled: false,
              child: AppLockScreen(),
            ),
          ),
      ],
    );
  }
}
