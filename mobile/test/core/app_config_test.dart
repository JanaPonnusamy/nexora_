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
    expect(config.apiBaseUrl, 'http://122.252.246.181:8443');
    expect(config.apiBaseUrl.endsWith('/'), isFalse);
    expect(config.apiBaseUrl, isNotEmpty);
    expect(config.enableVerboseLogging, isTrue);
    expect(config.isProd, isFalse);
  });

  group('transport security', () {
    // The constructor is exercised directly rather than through resolve():
    // resolve() reads compile-time --dart-defines, which a test cannot vary.
    AppConfig configFor(AppEnvironment env, String url) => AppConfig(
          environment: env,
          apiBaseUrl: url,
          connectTimeout: const Duration(seconds: 15),
          receiveTimeout: const Duration(seconds: 45),
          enableVerboseLogging: false,
        );

    test('isCleartext reflects the scheme', () {
      expect(
        configFor(AppEnvironment.staging, 'http://122.252.246.181:8443')
            .isCleartext,
        isTrue,
      );
      expect(
        configFor(AppEnvironment.prod, 'https://ho.axythic.com').isCleartext,
        isFalse,
      );
    });

    test('a prod build over cleartext is rejected, and says why', () {
      expect(
        () => configFor(AppEnvironment.prod, 'http://122.252.246.181:8443')
            .assertTransportSecurity(),
        throwsA(
          isA<StateError>().having(
            (e) => e.message,
            'message',
            allOf(contains('HTTPS'), contains('122.252.246.181')),
          ),
        ),
      );
    });

    test('cleartext outside prod is allowed — dev has no TLS yet', () {
      expect(
        () => configFor(AppEnvironment.dev, 'http://122.252.246.181:8443')
            .assertTransportSecurity(),
        returnsNormally,
      );
      expect(
        () => configFor(AppEnvironment.staging, 'http://122.252.246.181:8443')
            .assertTransportSecurity(),
        returnsNormally,
      );
    });

    test('a prod build over HTTPS passes', () {
      expect(
        () => configFor(AppEnvironment.prod, 'https://ho.axythic.com')
            .assertTransportSecurity(),
        returnsNormally,
      );
    });
  });
}
