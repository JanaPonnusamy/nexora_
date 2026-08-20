import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/app.dart';
import 'package:nexora_mobile/core/config/app_config.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/observability/crash_reporter.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';

/// Composition root: resolves configuration, initialises cross-cutting services
/// (logging, crash capture), and builds the Riverpod [ProviderScope] with the
/// concrete [AppConfig] injected. `main.dart` simply calls this.
Future<void> bootstrap() async {
  final reporter = LoggingCrashReporter();

  // Everything, including the binding, runs inside the guarded zone: an error
  // thrown during startup is exactly the one worth capturing, and it happens
  // before any in-app surface exists to report it.
  installCrashHandlers(
    reporter,
    run: () {
      WidgetsFlutterBinding.ensureInitialized();

      final config = AppConfig.resolve();
      AppLogger.init(verbose: config.enableVerboseLogging);
      AppLogger.of('Bootstrap').info(
        'Starting Axythic (${config.environment.name}) → ${config.apiBaseUrl}'
        '${config.isCleartext ? ' [cleartext]' : ''}',
      );

      runApp(
        ProviderScope(
          overrides: [
            appConfigProvider.overrideWithValue(config),
            crashReporterProvider.overrideWithValue(reporter),
          ],
          child: const NexoraApp(),
        ),
      );
    },
  );
}
