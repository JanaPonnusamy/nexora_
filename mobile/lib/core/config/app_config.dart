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
  /// `http://122.252.246.181:8443`. Endpoint paths (`/api/...`) are appended by the
  /// Dio client.
  final String apiBaseUrl;

  final Duration connectTimeout;
  final Duration receiveTimeout;
  final bool enableVerboseLogging;

  bool get isProd => environment == AppEnvironment.prod;

  /// True when the backend is addressed over plain HTTP.
  ///
  /// Worth surfacing even where it is permitted: every request, including the
  /// bearer token, is readable by anything on the path. Diagnostics screens show
  /// it so "why is this dev build talking to a server the release build cannot
  /// reach" has a visible answer.
  bool get isCleartext => apiBaseUrl.startsWith('http://');

  static const String _envName =
      String.fromEnvironment('NEXORA_ENV', defaultValue: 'dev');

  static const String _apiBaseUrlOverride =
      String.fromEnvironment('NEXORA_API_BASE_URL');

  /// Default base URLs per environment.
  ///
  /// The development and staging defaults use the remotely reachable HO host,
  /// so physical Android devices do not try to connect to their own localhost.
  /// Override this with `--dart-define=NEXORA_API_BASE_URL=...` when needed.
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
  ///
  /// Throws if a production build is pointed at a cleartext URL. That is a
  /// misconfiguration with no safe reading: the platforms block cleartext in a
  /// release build anyway, so the alternative to failing here is an app that
  /// installs, launches, and then fails every network call with a transport
  /// error that names nothing. Failing at resolve time names the cause, and it
  /// fails on the first launch of a bad build rather than in a user's hands.
  factory AppConfig.resolve() {
    final env = _resolveEnv();
    final baseUrl = _apiBaseUrlOverride.isNotEmpty
        ? _apiBaseUrlOverride
        : _defaultBaseUrl(env);

    return AppConfig(
      environment: env,
      apiBaseUrl: _stripTrailingSlash(baseUrl),
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 45),
      enableVerboseLogging: env != AppEnvironment.prod,
    )..assertTransportSecurity();
  }

  /// Public so it is testable: [AppConfig.resolve] reads compile-time
  /// `--dart-define`s, which a test cannot vary.
  void assertTransportSecurity() {
    if (isProd && isCleartext) {
      throw StateError(
        'Production builds must use HTTPS. NEXORA_API_BASE_URL is "$apiBaseUrl". '
        'Android (targetSdk 28+) and iOS ATS both block cleartext in a release '
        'build, so this configuration cannot reach the backend at all.',
      );
    }
  }

  static String _stripTrailingSlash(String url) =>
      url.endsWith('/') ? url.substring(0, url.length - 1) : url;
}
