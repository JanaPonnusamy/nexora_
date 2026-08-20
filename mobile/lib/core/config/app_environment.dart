/// Build-time environment selection for the Nexora mobile app.
///
/// The active environment is chosen at build time via a --dart-define, e.g.
///   flutter run --dart-define=NEXORA_ENV=staging
///
/// The API base URL can be overridden independently (useful because the HO
/// backend is reachable at different hosts from an emulator, a device on the
/// LAN, or a static IP):
///   flutter run --dart-define=NEXORA_API_BASE_URL=http://122.252.246.181:8443
enum AppEnvironment { dev, staging, prod }

extension AppEnvironmentX on AppEnvironment {
  String get label => switch (this) {
        AppEnvironment.dev => 'Development',
        AppEnvironment.staging => 'Staging',
        AppEnvironment.prod => 'Production',
      };
}
