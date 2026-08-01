import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/app.dart';
import 'package:nexora_mobile/core/config/app_config.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';

/// Composition root: resolves configuration, initialises cross-cutting services
/// (logging), and builds the Riverpod [ProviderScope] with the concrete
/// [AppConfig] injected. `main.dart` simply calls this.
Future<void> bootstrap() async {
  WidgetsFlutterBinding.ensureInitialized();

  final config = AppConfig.resolve();
  AppLogger.init(verbose: config.enableVerboseLogging);
  AppLogger.of('Bootstrap').info(
    'Starting Nexora (${config.environment.name}) → ${config.apiBaseUrl}',
  );

  runApp(
    ProviderScope(
      overrides: [
        appConfigProvider.overrideWithValue(config),
      ],
      child: const NexoraApp(),
    ),
  );
}
