import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/router/app_router.dart';
import 'package:nexora_mobile/core/security/app_lock_controller.dart';
import 'package:nexora_mobile/core/security/presentation/app_lock_gate.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/procurement/application/purchase_workspace_providers.dart';

/// Root widget. Kicks off session restoration once, then hands routing to
/// GoRouter (which redirects off [AuthState]).
class NexoraApp extends ConsumerStatefulWidget {
  const NexoraApp({super.key});

  @override
  ConsumerState<NexoraApp> createState() => _NexoraAppState();
}

class _NexoraAppState extends ConsumerState<NexoraApp> {
  static const _minimumSplashDuration = Duration(milliseconds: 1800);

  @override
  void initState() {
    super.initState();
    // Restore any persisted session after the first frame so provider reads are
    // safe. The splash screen is shown until this resolves.
    WidgetsBinding.instance
        .addPostFrameCallback((_) => unawaited(_bootstrap()));
  }

  Future<void> _bootstrap() async {
    try {
      await Future.wait<void>([
        ref.read(authControllerProvider.notifier).bootstrap(),
        // Reads the stored unlock preference and, if set, locks before the
        // first frame of real content.
        ref.read(appLockControllerProvider.notifier).bootstrap(),
        // Avoid a one-frame branded splash when secure storage resolves fast.
        Future<void>.delayed(_minimumSplashDuration),
      ]);
    } finally {
      if (mounted) {
        ref.read(startupSplashProvider.notifier).state = false;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // Boot the Legacy Store Agent (device registration, config download, health
    // monitoring, sync engine) the moment the session becomes ready. Idempotent.
    ref.listen(authControllerProvider, (prev, next) {
      final becameReady = next.isReady && !(prev?.isReady ?? false);
      if (becameReady) {
        // Tags every subsequent report with who and where, so a crash can be
        // matched to the support call that follows it.
        ref.read(crashReporterProvider).setUser(
              userId: next.user?.userId,
              storeId: next.selectedStore?.storeId,
            );
        ref.read(agentManagerProvider).initialize();
        // Captures taken offline have to upload without anyone asking. All
        // three calls are idempotent, so a re-login does not double up.
        ref.read(captureSyncCoordinatorProvider).start();
        // Teach the outbox how to send review edits before starting the drain,
        // or the first pass finds entries it has no handler for and gives up
        // on them permanently.
        ref.read(reviewOutboxHandlersProvider);
        ref.read(purchaseOutboxHandlersProvider);
        ref.read(outboxCoordinatorProvider).start();
      }
    });

    final router = ref.watch(routerProvider);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      // Paint the status/navigation bars to match the app canvas rather than
      // letting the OS default flash through on push/pop.
      value: AppTheme.systemOverlay,
      child: MaterialApp.router(
        title: 'Axythic',
        debugShowCheckedModeBanner: false,
        // Dark is the product's only theme — `theme` and `darkTheme` are both
        // set so no code path can fall back to a Material default.
        theme: AppTheme.dark,
        darkTheme: AppTheme.dark,
        themeMode: ThemeMode.dark,
        routerConfig: router,
        // Wrapping here rather than at a route puts the lock over every
        // navigator, including the root one the camera is pushed onto.
        builder: (_, child) =>
            AppLockGate(child: child ?? const SizedBox.shrink()),
      ),
    );
  }
}
