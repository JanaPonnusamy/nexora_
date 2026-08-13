import 'package:nexora_mobile/core/config/app_environment.dart';

/// Immutable, environment-resolved application configuration.
///
/// Values are read from `--dart-define` at build time with safe defaults so the
/// app runs from source with no extra flags. Nothing here is a secret — the
/// backend remains the single source of truth and the only authority on auth.
class AppConfig {
  const AppConfig({
    required this.environment,
    required this.apiBaseUrl,
    required this.connectTimeout,
    required this.receiveTimeout,
    required this.enableVerboseLogging,
  });

  final AppEnvironment environment;

  /// Root of the FastAPI backend, WITHOUT a trailing slash, e.g.
  /// `http://10.0.2.2:8000`. Endpoint paths (`/api/...`) are appended by the
  /// Dio client.
  final String apiBaseUrl;

  final Duration connectTimeout;
  final Duration receiveTimeout;
  final bool enableVerboseLogging;

  bool get isProd => environment == AppEnvironment.prod;

  static const String _envName =
      String.fromEnvironment('NEXORA_ENV', defaultValue: 'dev');

  static const String _apiBaseUrlOverride =
      String.fromEnvironment('NEXORA_API_BASE_URL');

  /// Default base URLs per environment.
  ///
  /// NOTE: `10.0.2.2` is how the Android emulator reaches the host machine's
  /// `localhost`. On a physical device use the HO's LAN IP via
  /// `--dart-define=NEXORA_API_BASE_URL=...`. iOS simulator can use
  /// `http://localhost:8000` directly.
  static String _defaultBaseUrl(AppEnvironment env) => switch (env) {
        AppEnvironment.dev => 'http://122.252.246.181:8443',
        AppEnvironment.staging => 'http://122.252.246.181:8443',
        AppEnvironment.prod => 'https://ho.nexora.local',
      };

  static AppEnvironment _resolveEnv() => switch (_envName.toLowerCase()) {
        'prod' || 'production' => AppEnvironment.prod,
        'staging' || 'stage' => AppEnvironment.staging,
        _ => AppEnvironment.dev,
      };

  /// Builds the effective configuration for the current build.
  factory AppConfig.resolve() {
    final env = _resolveEnv();
    final baseUrl =
        _apiBaseUrlOverride.isNotEmpty ? _apiBaseUrlOverride : _defaultBaseUrl(env);

    return AppConfig(
      environment: env,
      apiBaseUrl: _stripTrailingSlash(baseUrl),
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 45),
      enableVerboseLogging: env != AppEnvironment.prod,
    );
  }

  static String _stripTrailingSlash(String url) =>
      url.endsWith('/') ? url.substring(0, url.length - 1) : url;
}
