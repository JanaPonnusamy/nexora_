import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/router/app_router.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';

/// Root widget. Kicks off session restoration once, then hands routing to
/// GoRouter (which redirects off [AuthState]).
class NexoraApp extends ConsumerStatefulWidget {
  const NexoraApp({super.key});

  @override
  ConsumerState<NexoraApp> createState() => _NexoraAppState();
}

class _NexoraAppState extends ConsumerState<NexoraApp> {
  @override
  void initState() {
    super.initState();
    // Restore any persisted session after the first frame so provider reads are
    // safe. The splash screen is shown until this resolves.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(authControllerProvider.notifier).bootstrap();
    });
  }

  @override
  Widget build(BuildContext context) {
    // Boot the Legacy Store Agent (device registration, config download, health
    // monitoring, sync engine) the moment the session becomes ready. Idempotent.
    ref.listen(authControllerProvider, (prev, next) {
      final becameReady = next.isReady && !(prev?.isReady ?? false);
      if (becameReady) {
        ref.read(agentManagerProvider).initialize();
      }
    });

    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'Nexora',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      // Default to the light theme regardless of the OS/browser preference —
      // the product's primary, polished surface is light (matches the HO web
      // console). Dark remains available/defined for a future in-app toggle.
      themeMode: ThemeMode.light,
      routerConfig: router,
    );
  }
}
