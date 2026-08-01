import 'package:flutter_test/flutter_test.dart';
import 'package:nexora_mobile/core/config/app_config.dart';
import 'package:nexora_mobile/core/config/app_environment.dart';

/// Codegen-free smoke test: verifies environment resolution and base-URL
/// normalisation. Runs with plain `flutter test` (no build_runner needed).
void main() {
  test('AppConfig.resolve defaults to dev with a trailing-slash-free base URL',
      () {
    final config = AppConfig.resolve();

    // No --dart-define supplied in a bare test run → dev environment.
    expect(config.environment, AppEnvironment.dev);
    expect(config.apiBaseUrl.endsWith('/'), isFalse);
    expect(config.apiBaseUrl, isNotEmpty);
    expect(config.enableVerboseLogging, isTrue);
    expect(config.isProd, isFalse);
  });
}
